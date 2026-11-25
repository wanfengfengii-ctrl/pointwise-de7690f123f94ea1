from dataclasses import dataclass

from issue.coverage import IssueCoverage
from survey.revision_store import FrozenRevision


@dataclass(frozen=True)
class LocalRoute:
    # Each position is held only in the source station.
    cells: tuple[str, ...]
    terminal: dict


def _walk(topology, exits, anchor):
    path = {}
    cell = anchor
    while cell not in path:
        path[cell] = len(path)
        if cell in topology.outlets:
            return LocalRoute(tuple(path), {
                'kind': 'outlet', 'outlet': topology.outlets[cell], 'hops': len(path) - 1,
            })
        if cell in exits:
            piece, port = exits[cell]
            return LocalRoute(tuple(path), {
                'kind': 'seam', 'piece': piece, 'port': port, 'hops': len(path),
            })
        cell = topology.successors[cell]

    entry = path[cell]
    return LocalRoute(tuple(path), {
        'kind': 'loop', 'entry_hops': entry, 'loop_length': len(path) - entry,
    })


def walk_local_routes(revision: FrozenRevision, coverage: IssueCoverage, piece, anchors):
    topology = revision.topology
    routes = {}
    for name, cell in anchors.items():
        if topology.cells.get(cell) != piece:
            raise ValueError(f'route anchor is outside piece {piece}')
        routes[name] = _walk(topology, coverage.exits, cell)
    return routes
