from itertools import combinations

from issue.coverage import IssueCoverage
from issue.segments import walk_local_routes
from survey.revision_store import FrozenRevision


def _shared_positions(routes):
    by_exit = {}
    for route_id, route in routes.items():
        terminal = route.terminal
        if terminal['kind'] == 'seam':
            exit_key = terminal['piece'], terminal['port']
            by_exit.setdefault(exit_key, []).append(route_id)

    positions = {
        route_id: {cell: offset for offset, cell in enumerate(routes[route_id].cells)}
        for group in by_exit.values() for route_id in group
    }
    joins = []
    for group in by_exit.values():
        for left, right in combinations(sorted(group), 2):
            right_positions = positions[right]
            for offset, cell in enumerate(routes[left].cells):
                if cell in right_positions:
                    joins.append([left, right, offset, right_positions[cell]])
                    break
    return sorted(joins)


def derive_piece_body(revision: FrozenRevision, coverage: IssueCoverage, piece):
    if piece not in coverage.pieces:
        raise ValueError(f'piece {piece!r} is outside the frozen coverage')
    anchors = {}
    starts = {}
    for number, (name, cell) in enumerate(sorted(coverage.starts[piece].items()), 1):
        route_id = f's{number}'
        anchors[route_id] = cell
        starts[name] = route_id

    incoming = {}
    for number, (port, (source, cell)) in enumerate(sorted(coverage.inlets[piece].items()), 1):
        route_id = f'i{number}'
        anchors[route_id] = cell
        incoming[port] = {'from_piece': source, 'route': route_id}

    routes = walk_local_routes(revision, coverage, piece, anchors)
    return {
        'survey': revision.topology.survey,
        'revision': revision.revision_id,
        'piece': piece,
        'coverage': list(coverage.pieces),
        'starts': starts,
        'incoming': incoming,
        'routes': {name: route.terminal for name, route in routes.items()},
        'joins': _shared_positions(routes),
    }
