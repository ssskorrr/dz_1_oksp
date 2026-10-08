import base64
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import app
from db import connect
from seed import seed

AUTH={'Authorization':'Basic '+base64.b64encode(b'demo:demo').decode()}

@pytest.fixture(scope='module',autouse=True)
def data(): seed('small')

@pytest.fixture
def client():
    app.config['TESTING']=True
    return app.test_client()

def test_requires_auth(client): assert client.get('/api/bookings').status_code==401
def test_wrong_password(client): assert client.get('/api/services',headers={'Authorization':'Basic ZGVtbzpiYWQ='}).status_code==401
def test_pagination_contract(client):
    r=client.get('/api/bookings?status=all&page=1&size=7',headers=AUTH)
    assert r.status_code==200 and len(r.json['items'])==7 and r.json['total']==300
def test_bad_pagination(client): assert client.get('/api/bookings?size=0',headers=AUTH).status_code==422
def test_bad_status(client): assert client.get('/api/bookings?status=unknown',headers=AUTH).status_code==422
def test_missing_card(client): assert client.get('/api/bookings/99999',headers=AUTH).status_code==404
def test_card_contract(client):
    r=client.get('/api/bookings/1',headers=AUTH)
    assert r.status_code==200 and {'specialist','service','starts_at','duration_minutes'}<=r.json.keys()
def test_invalid_booking(client): assert client.post('/api/bookings',json={'slot_id':True,'service_id':1},headers=AUTH).status_code==422
def test_specialty_mismatch(client): assert client.post('/api/bookings',json={'slot_id':401,'service_id':2},headers=AUTH).status_code==422
def test_existing_overlap(client): assert client.post('/api/bookings',json={'slot_id':1,'service_id':1},headers=AUTH).status_code==409
def test_booking_cancel_releases_slot(client):
    r=client.post('/api/bookings',json={'slot_id':401,'service_id':1},headers=AUTH)
    assert r.status_code==201
    assert client.post('/api/bookings',json={'slot_id':401,'service_id':1},headers=AUTH).status_code==409
    assert client.post(f"/api/bookings/{r.json['id']}/cancel",headers=AUTH).json['status']=='cancelled'
    again=client.post('/api/bookings',json={'slot_id':401,'service_id':1},headers=AUTH)
    assert again.status_code==201
    client.post(f"/api/bookings/{again.json['id']}/cancel",headers=AUTH)
def test_concurrent_booking_one_winner():
    def attempt(_):
        with app.test_client() as c: return c.post('/api/bookings',json={'slot_id':411,'service_id':1},headers=AUTH).status_code
    with ThreadPoolExecutor(max_workers=2) as executor: assert sorted(executor.map(attempt,range(2)))==[201,409]
def test_period_invalid(client): assert client.get('/api/summary?from=2027-01-01&to=2026-01-01',headers=AUTH).status_code==422
def test_summary_consistency(client):
    r=client.get('/api/summary',headers=AUTH)
    assert r.status_code==200 and len(r.json['items'])==10
    assert r.json['total_bookings']==sum(x['total'] for x in r.json['items'])
def test_timing_headers(client):
    r=client.get('/api/services',headers=AUTH)
    assert float(r.headers['X-Total-Ms'])>=float(r.headers['X-DB-Ms'])>=0
    assert int(r.headers['X-DB-Queries'])==2
def test_available_slots(client):
    r=client.get('/api/slots?service_id=1&specialist_id=1',headers=AUTH)
    assert r.status_code==200 and r.json['total']>0
    assert len(r.json['items'])<=20
