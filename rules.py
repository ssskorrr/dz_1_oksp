def overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a

def valid_duration(slot_start, slot_end, minutes):
    return (slot_end - slot_start).total_seconds() >= minutes * 60

def cancellation_share(cancelled, total):
    return cancelled / total if total else 0.0
