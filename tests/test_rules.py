from datetime import datetime, timedelta
from rules import overlaps, valid_duration, cancellation_share

T=datetime(2026,11,1,9)

def test_overlap_is_rejected(): assert overlaps(T,T+timedelta(hours=1),T+timedelta(minutes=30),T+timedelta(hours=2))
def test_adjacent_slots_do_not_overlap(): assert not overlaps(T,T+timedelta(hours=1),T+timedelta(hours=1),T+timedelta(hours=2))
def test_exact_duration_fits(): assert valid_duration(T,T+timedelta(hours=1),60)
def test_long_service_does_not_fit(): assert not valid_duration(T,T+timedelta(minutes=30),60)
def test_empty_cancellation_share(): assert cancellation_share(0,0)==0
def test_cancellation_share(): assert cancellation_share(2,10)==0.2
