from dataclasses import dataclass

from survey.revision_store import FrozenRevision


@dataclass(frozen=True)
class IssueCoverage:
    pieces: tuple[str, ...]
    starts: dict[str, dict[str, str]]
    inlets: dict[str, dict[str, tuple[str, str]]]
    exits: dict[str, tuple[str, str]]


def derive_coverage(revision: FrozenRevision):
    topology = revision.topology
    starts = {piece: {} for piece in topology.pieces}
    for name, cell in topology.starts.items():
        starts[topology.cells[cell]][name] = cell

    crossings = {}
    for cell, target in topology.successors.items():
        source_piece = topology.cells[cell]
        target_piece = topology.cells[target]
        if source_piece != target_piece:
            crossings[cell] = (source_piece, target_piece, target)

    inlets = {piece: {} for piece in topology.pieces}
    ports = {}
    for number, crossing in enumerate(sorted(set(crossings.values())), 1):
        source_piece, target_piece, target = crossing
        port = f'p{number}'
        ports[crossing] = port
        inlets[target_piece][port] = (source_piece, target)

    exits = {
        cell: (crossing[1], ports[crossing]) for cell, crossing in crossings.items()
    }
    return IssueCoverage(topology.pieces, starts, inlets, exits)
