from dataclasses import dataclass

from receipt.selection import SelectedPieces


RouteKey = tuple[str, str]


@dataclass(frozen=True)
class ResolvedHandover:
    start: RouteKey
    routes: dict[RouteKey, dict]
    targets: dict[RouteKey, RouteKey]
    joins: dict[RouteKey, dict[RouteKey, tuple[int, int]]]


def resolve_ports(selected: SelectedPieces, start):
    starts = {}
    routes = {}
    targets = {}
    joins = {}
    for name, piece in selected.pieces.items():
        for public_point, route_id in piece.starts.items():
            if public_point in starts:
                raise ValueError(f'ambiguous public start {public_point}')
            starts[public_point] = (name, route_id)
        for route_id, route in piece.routes.items():
            key = name, route_id
            routes[key] = route
            if route['kind'] == 'seam':
                destination = selected.pieces[route['piece']]
                inlet = destination.incoming.get(route['port'])
                if inlet is None or inlet['from_piece'] != name:
                    raise ValueError(f'unresolved seam from {name} to {destination.piece} at {route["port"]}')
                targets[key] = (destination.piece, inlet['route'])
        for left, right, left_offset, right_offset in piece.joins:
            a, b = (name, left), (name, right)
            joins.setdefault(a, {})[b] = left_offset, right_offset
            joins.setdefault(b, {})[a] = right_offset, left_offset
    if not isinstance(start, str) or start not in starts:
        raise ValueError(f'unknown public start {start!r}')
    return ResolvedHandover(starts[start], routes, targets, joins)
