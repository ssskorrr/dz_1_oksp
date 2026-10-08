import argparse
import base64
import json
import math
import statistics
import time
import urllib.request
from pathlib import Path
from seed import seed

BASE='http://127.0.0.1:8089/api/'
AUTH='Basic '+base64.b64encode(b'demo:demo').decode()
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path,method='GET',payload=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':AUTH,'Content-Type':'application/json'},method=method)
    start=time.perf_counter()
    with OPENER.open(req,timeout=60) as r:
        body=json.load(r); wall=(time.perf_counter()-start)*1000
        return body,{'wall_ms':wall,'server_ms':float(r.headers['X-Total-Ms']),'db_ms':float(r.headers['X-DB-Ms']),'queries':int(r.headers['X-DB-Queries'])}

def run(size):
    initial=seed(size); repeated=seed(size)
    assert initial==repeated, 'Seed is not reproducible'
    n_spec=initial['counts']['specialists']; slot_id=initial['counts']['slots']-n_spec+1
    operations=[('GET /api/services',lambda:request('services')),
      ('GET /api/specialists',lambda:request('specialists')),
      ('GET /api/bookings',lambda:request('bookings?status=active&page=1&size=20')),
      ('GET /api/bookings/{id}',lambda:request('bookings/1')),
      ('GET /api/slots',lambda:request('slots?service_id=1&specialist_id=1&from=2026-11-01&to=2027-02-01')),
      ('GET /api/summary',lambda:request('summary?from=2026-11-01&to=2027-02-01'))]
    def create():
        body,metrics=request('bookings','POST',{'slot_id':slot_id,'service_id':1})
        request(f"bookings/{body['id']}/cancel",'POST',{})
        return body,metrics
    def cancel():
        body,_=request('bookings','POST',{'slot_id':slot_id,'service_id':1})
        return request(f"bookings/{body['id']}/cancel",'POST',{})
    operations += [('POST /api/bookings',create),('POST /api/bookings/{id}/cancel',cancel)]
    results=[]
    for name,operation in operations:
        for _ in range(5): operation()
        samples=[operation()[1] for _ in range(30)]
        walls=sorted(x['wall_ms'] for x in samples)
        results.append({'operation':name,'p50':statistics.median(walls),'p95':walls[math.ceil(.95*len(walls))-1],'max':max(walls),
          'server_ms':statistics.mean(x['server_ms'] for x in samples),'db_ms':statistics.mean(x['db_ms'] for x in samples),
          'queries':statistics.mean(x['queries'] for x in samples),'samples':samples})
        print(name,round(results[-1]['p50'],3),flush=True)
    result={'initial':initial,'reproducible':True,'warmup':5,'repeats':30,'added_bookings':70,'operations':results}
    Path('evidence').mkdir(exist_ok=True)
    Path(f'evidence/{size}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('size',choices=['small','work']); run(parser.parse_args().size)
