import base64
import hashlib
import hmac
import os
import time
from datetime import datetime
from flask import Flask, g, jsonify, request, render_template, abort
from werkzeug.security import check_password_hash
from db import DSN, Database
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from rules import valid_duration

app=Flask(__name__)
app.json.ensure_ascii=False
pool=ConnectionPool(DSN,min_size=1,max_size=4,kwargs={'row_factory':dict_row,'options':'-c max_parallel_workers_per_gather=0 -c jit=off'},open=True)

def error(code,message):
    abort(code,description=message)

def integer(name, default=None, maximum=1000000):
    value=request.args.get(name,default)
    try:
        value=int(value)
        if not 1<=value<=maximum: raise ValueError()
        return value
    except (TypeError,ValueError): error(422,f'Некорректный параметр {name}')

def period():
    try:
        start=datetime.fromisoformat(request.args.get('from','2026-11-01'))
        end=datetime.fromisoformat(request.args.get('to','2027-02-01'))
        if end<=start: raise ValueError()
        return start,end
    except ValueError: error(422,'Некорректный период')

@app.before_request
def begin():
    g.started=time.perf_counter()
    if not request.path.startswith('/api/'): return
    g.conn=pool.getconn(); g.conn.execute('SET search_path TO kirill_skorikov'); g.db=Database(g.conn)
    auth=request.authorization
    if not auth or auth.type!='basic': error(401,'Требуется Basic авторизация')
    user=g.db.one('SELECT * FROM app_users WHERE username=%s',(auth.username,))
    valid=False
    if user:
        if user['password_hash'].startswith('demo-sha256:'):
            valid=hmac.compare_digest(user['password_hash'][12:],hashlib.sha256((auth.password or '').encode()).hexdigest())
        else: valid=check_password_hash(user['password_hash'],auth.password or '')
    if not valid: error(401,'Неверные учетные данные')
    g.user_id=user['id']

@app.after_request
def timing(response):
    elapsed=(time.perf_counter()-g.started)*1000
    db=getattr(g,'db',None)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Total-Ms']=f'{elapsed:.3f}'
    response.headers['X-DB-Ms']=f'{db.ms if db else 0:.3f}'
    response.headers['X-DB-Queries']=str(db.count if db else 0)
    if response.status_code==401: response.headers['WWW-Authenticate']='Basic realm="kirill_skorikov"'
    return response

@app.teardown_request
def finish(exception):
    conn=g.pop('conn',None)
    if conn:
        try:
            if not conn.closed: conn.rollback()
        finally:
            pool.putconn(conn)

@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(422)
def api_error(exc):
    return jsonify(error=exc.description),exc.code

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/services')
def services(): return jsonify(items=g.db.query('SELECT * FROM services ORDER BY id'))

@app.get('/api/specialists')
def specialists(): return jsonify(items=g.db.query('SELECT * FROM specialists ORDER BY id'))

@app.get('/api/slots')
def slots():
    service_id=integer('service_id'); specialist_id=integer('specialist_id'); page=integer('page',1); size=integer('size',20,100)
    start,end=period()
    service=g.db.one('SELECT * FROM services WHERE id=%s',(service_id,))
    specialist=g.db.one('SELECT * FROM specialists WHERE id=%s',(specialist_id,))
    if not service or not specialist: error(404,'Услуга или специалист не найдены')
    if service['specialty']!=specialist['specialty']: return jsonify(items=[],total=0,page=page,size=size)
    where="""s.specialist_id=%s AND s.starts_at>=%s AND s.starts_at<%s
      AND s.ends_at-s.starts_at >= %s*interval '1 minute'
      AND NOT EXISTS(SELECT 1 FROM bookings b JOIN slots bs ON bs.id=b.slot_id
        WHERE b.status='active' AND bs.specialist_id=s.specialist_id
        AND bs.starts_at<s.ends_at AND s.starts_at<bs.ends_at)"""
    params=(specialist_id,start,end,service['duration_minutes'])
    total=g.db.one('SELECT count(*) AS n FROM slots s WHERE '+where,params)['n']
    items=g.db.query('SELECT s.* FROM slots s WHERE '+where+' ORDER BY s.starts_at,s.id LIMIT %s OFFSET %s',params+(size,(page-1)*size))
    return jsonify(items=items,total=total,page=page,size=size)

@app.get('/api/bookings')
def bookings():
    page=integer('page',1); size=integer('size',20,100); status=request.args.get('status','active')
    if status not in ('active','cancelled','all'): error(422,'Неизвестный статус')
    where='b.user_id=%s'; params=(g.user_id,)
    if status!='all': where+=' AND b.status=%s'; params+=(status,)
    total=g.db.one('SELECT count(*) AS n FROM bookings b WHERE '+where,params)['n']
    items=g.db.query('''SELECT b.*,s.starts_at,s.ends_at,p.name AS specialist,v.name AS service
      FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN specialists p ON p.id=s.specialist_id
      JOIN services v ON v.id=b.service_id WHERE '''+where+' ORDER BY b.id LIMIT %s OFFSET %s',params+(size,(page-1)*size))
    return jsonify(items=items,total=total,page=page,size=size)

@app.get('/api/bookings/<int:booking_id>')
def card(booking_id):
    row=g.db.one('''SELECT b.*,s.starts_at,s.ends_at,p.id AS specialist_id,p.name AS specialist,
      v.name AS service,v.duration_minutes FROM bookings b JOIN slots s ON s.id=b.slot_id
      JOIN specialists p ON p.id=s.specialist_id JOIN services v ON v.id=b.service_id
      WHERE b.id=%s AND b.user_id=%s''',(booking_id,g.user_id))
    if not row: error(404,'Запись не найдена')
    return jsonify(row)

@app.post('/api/bookings')
def book():
    data=request.get_json(silent=True) or {}
    if any(type(data.get(k))!=int or data[k]<1 for k in ('slot_id','service_id')): error(422,'slot_id и service_id должны быть положительными целыми')
    # One transaction and per-specialist advisory lock serialize overlapping reservations.
    with g.conn.transaction():
        slot=g.db.one('SELECT * FROM slots WHERE id=%s',(data['slot_id'],))
        service=g.db.one('SELECT * FROM services WHERE id=%s',(data['service_id'],))
        if not slot or not service: error(404,'Слот или услуга не найдены')
        g.db.query('SELECT pg_advisory_xact_lock(20261008,%s)',(slot['specialist_id'],))
        specialist=g.db.one('SELECT * FROM specialists WHERE id=%s',(slot['specialist_id'],))
        if service['specialty']!=specialist['specialty']: error(422,'Специализация не совпадает')
        if not valid_duration(slot['starts_at'],slot['ends_at'],service['duration_minutes']): error(422,'Недостаточная длительность слота')
        conflict=g.db.one('''SELECT b.id FROM bookings b JOIN slots s ON s.id=b.slot_id
          WHERE b.status='active' AND s.specialist_id=%s AND s.starts_at<%s AND %s<s.ends_at LIMIT 1''',(slot['specialist_id'],slot['ends_at'],slot['starts_at']))
        if conflict: error(409,'Слот пересекается с активной записью')
        row=g.db.one("INSERT INTO bookings(user_id,service_id,slot_id,status) VALUES(%s,%s,%s,'active') RETURNING *",(g.user_id,data['service_id'],data['slot_id']))
    g.conn.commit()
    return jsonify(row),201

@app.post('/api/bookings/<int:booking_id>/cancel')
def cancel(booking_id):
    row=g.db.one("UPDATE bookings SET status='cancelled' WHERE id=%s AND user_id=%s RETURNING *",(booking_id,g.user_id))
    if not row: error(404,'Запись не найдена')
    g.conn.commit()
    return jsonify(row)

@app.get('/api/summary')
def summary():
    start,end=period()
    items=g.db.query('''WITH capacities AS (
      SELECT specialist_id,sum(extract(epoch FROM (ends_at-starts_at))/60) AS minutes
      FROM slots WHERE starts_at>=%s AND starts_at<%s GROUP BY specialist_id
    ), counts AS (
      SELECT s.specialist_id,count(*) AS total,count(*) FILTER(WHERE b.status='cancelled') AS cancelled,
       COALESCE(sum(v.duration_minutes) FILTER(WHERE b.status='active'),0) AS booked_minutes
      FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN services v ON v.id=b.service_id
      WHERE s.starts_at>=%s AND s.starts_at<%s GROUP BY s.specialist_id
    ) SELECT p.id,p.name,COALESCE(c.total,0)::int AS total,COALESCE(c.cancelled,0)::int AS cancelled,
     COALESCE(c.booked_minutes,0)::float AS booked_minutes,COALESCE(a.minutes,0)::float AS available_minutes
     FROM specialists p LEFT JOIN capacities a ON a.specialist_id=p.id LEFT JOIN counts c ON c.specialist_id=p.id ORDER BY p.id''',(start,end,start,end))
    for row in items:
        row['utilization']=row['booked_minutes']/row['available_minutes'] if row['available_minutes'] else 0
        row['cancellation_share']=row['cancelled']/row['total'] if row['total'] else 0
    return jsonify(items=items,total_bookings=sum(r['total'] for r in items),cancelled=sum(r['cancelled'] for r in items))

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('APP_PORT','8089')),debug=False,threaded=True,use_reloader=False)
