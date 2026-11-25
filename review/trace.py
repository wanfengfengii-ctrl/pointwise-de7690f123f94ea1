from review.outcomes import LoopOutcome, OutletOutcome
from review.ports import ResolvedHandover


def _first_repeat(handover, route_key, hops, seen):
    matches = (
        (offset, seen[previous] + previous_offset)
        for previous, (offset, previous_offset) in handover.joins.get(route_key, {}).items()
        if previous in seen
    )
    match = min(matches, default=None)
    if match is None:
        return None
    offset, first_arrival = match
    return LoopOutcome(first_arrival, hops + offset - first_arrival)


def trace_handover(handover: ResolvedHandover):
    route_key = handover.start
    seen = {}
    hops = 0
    while route_key not in seen:
        repeated = _first_repeat(handover, route_key, hops, seen)
        if repeated is not None:
            return repeated
        route = handover.routes[route_key]
        kind = route['kind']
        if kind == 'outlet':
            return OutletOutcome(route['outlet'], hops + route['hops'])
        if kind == 'loop':
            return LoopOutcome(hops + route['entry_hops'], route['loop_length'])
        seen[route_key] = hops
        hops += route['hops']
        route_key = handover.targets[route_key]
    entry = seen[route_key]
    return LoopOutcome(entry, hops - entry)
