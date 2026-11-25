from dataclasses import dataclass

from issue.envelope import decode_envelope


@dataclass(frozen=True)
class VerifiedPiece:
    issue_id: str
    raw: bytes
    survey: str
    revision_id: str
    piece: str
    coverage: tuple[str, ...]
    starts: dict[str, str]
    incoming: dict[str, dict]
    routes: dict[str, dict]
    joins: tuple[tuple[str, str, int, int], ...]


def _identifier(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('expected a nonempty piece identifier')
    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError('invalid character in piece identifier')
    return value


def _fields(record, names, description):
    if not isinstance(record, dict) or record.keys() != names:
        raise ValueError(f'invalid {description} fields')


def _steps(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'hop count must be an integer at least {minimum}')


def _other_piece(target, piece, coverage):
    if _identifier(target) == piece or target not in coverage:
        raise ValueError('a seam must connect two distinct declared pieces')


def _validate_route(route, piece, coverage):
    if not isinstance(route, dict):
        raise ValueError('invalid route')
    kind = route.get('kind')
    if kind == 'seam':
        _fields(route, {'kind', 'piece', 'port', 'hops'}, 'seam route')
        _other_piece(route['piece'], piece, coverage)
        _identifier(route['port'])
        _steps(route['hops'], 1)
    elif kind == 'outlet':
        _fields(route, {'kind', 'outlet', 'hops'}, 'outlet route')
        _identifier(route['outlet'])
        _steps(route['hops'])
    elif kind == 'loop':
        _fields(route, {'kind', 'entry_hops', 'loop_length'}, 'local loop route')
        _steps(route['entry_hops'])
        _steps(route['loop_length'], 1)
    else:
        raise ValueError('unknown route terminal')


def _validate_anchors(starts, incoming, routes, piece, coverage):
    if any(not isinstance(table, dict) for table in (starts, incoming, routes)):
        raise ValueError('start, incoming and route tables must be objects')
    anchors = []
    for name, route_id in starts.items():
        _identifier(name)
        anchors.append(_identifier(route_id))
    for port, inlet in incoming.items():
        _identifier(port)
        _fields(inlet, {'from_piece', 'route'}, 'incoming port')
        _other_piece(inlet['from_piece'], piece, coverage)
        anchors.append(_identifier(inlet['route']))
    if set(anchors) != routes.keys() or len(anchors) != len(routes):
        raise ValueError('each public start and inlet must own exactly one route')
    for route in routes.values():
        _validate_route(route, piece, coverage)


def _validate_joins(rows, routes):
    if not isinstance(rows, list):
        raise ValueError('joins must be an array')
    pairs = set()
    verified = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('a join requires two routes and two offsets')
        left, right, left_hops, right_hops = row
        pair = _identifier(left), _identifier(right)
        if left >= right or pair in pairs or left not in routes or right not in routes:
            raise ValueError('invalid or duplicate join route pair')
        _steps(left_hops)
        _steps(right_hops)
        a, b = routes[left], routes[right]
        if (
            a['kind'] != 'seam' or b['kind'] != 'seam'
            or (a['piece'], a['port']) != (b['piece'], b['port'])
        ):
            raise ValueError('joined routes must leave by the same port')
        remaining = a['hops'] - left_hops
        if remaining <= 0 or remaining != b['hops'] - right_hops:
            raise ValueError('join offsets must share a positive distance to the seam')
        pairs.add(pair)
        verified.append((left, right, left_hops, right_hops))
    return tuple(verified)


def validate_piece(raw):
    issue_id, body = decode_envelope(raw)
    _fields(body, {'survey', 'revision', 'piece', 'coverage', 'starts', 'incoming', 'routes', 'joins'}, 'piece body')
    survey = _identifier(body['survey'])
    revision = _identifier(body['revision'])
    piece = _identifier(body['piece'])
    if not isinstance(body['coverage'], list):
        raise ValueError('coverage must be an array')
    names = [_identifier(name) for name in body['coverage']]
    coverage = frozenset(names)
    if len(coverage) != len(names) or piece not in coverage:
        raise ValueError('coverage must contain the current piece and no duplicates')
    starts, incoming, routes = (body[key] for key in ('starts', 'incoming', 'routes'))
    _validate_anchors(starts, incoming, routes, piece, coverage)
    joins = _validate_joins(body['joins'], routes)
    return VerifiedPiece(issue_id, raw, survey, revision, piece, tuple(sorted(coverage)), starts, incoming, routes, joins)
