from review.outcomes import LoopOutcome, OutletOutcome
from survey.revision_store import FrozenRevision


def trace_reference(revision: FrozenRevision, start):
    topology = revision.topology
    if not isinstance(start, str) or start not in topology.starts:
        raise ValueError(f'unknown public start {start!r}')
    cell = topology.starts[start]
    arrivals = {}
    hops = 0
    while cell not in arrivals:
        if cell in topology.outlets:
            return OutletOutcome(topology.outlets[cell], hops)
        arrivals[cell] = hops
        cell = topology.successors[cell]
        hops += 1
    entry = arrivals[cell]
    return LoopOutcome(entry, hops - entry)


def online(store, revision_id, start):
    return trace_reference(store.load(revision_id), start)
