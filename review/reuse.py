from dataclasses import dataclass

from hashlib import sha256

from issue.declaration import decode_declaration, digest_declaration
from receipt.coverage import check_coverage
from reports.publication import publish_report
from review.ports import ResolvedHandover
from review.trace import trace_handover


@dataclass(frozen=True)
class ReuseSelection:
    survey: str
    revision_id: str
    provenance: tuple[tuple[str, int], ...]


DECLARATION_FIELDS = {
    'survey', 'piece', 'old_issue', 'old_piece_sha256', 'old_revision',
    'target_revision', 'coverage', 'starts', 'inlets', 'seams', 'joins',
}


def _as_identifier(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('invalid identifier inside reuse declaration')
    return value


def _select_reuse_pieces(inventory, survey, target_revision, receipt_ids):
    if not isinstance(survey, str) or not survey or not isinstance(target_revision, str) or not target_revision:
        raise ValueError('expected a survey and target revision ID')
    try:
        ids = list(receipt_ids)
    except TypeError as error:
        raise ValueError('receipt IDs must be an iterable of integers') from error

    unique_ids = []
    for receipt_id in ids:
        if type(receipt_id) is not int:
            raise ValueError('receipt ID must be an integer')
        if receipt_id not in unique_ids:
            unique_ids.append(receipt_id)

    received = {}
    for receipt_id in unique_ids:
        piece = inventory.load(receipt_id)  # unknown id raises KeyError
        if piece.survey != survey:
            raise ValueError(f'receipt {receipt_id} belongs to another survey')
        received[receipt_id] = piece
    by_piece = check_coverage(received.items())
    pieces = {name: by_piece[name][1] for name in sorted(by_piece)}
    provenance = tuple((name, by_piece[name][0]) for name in sorted(by_piece))
    return pieces, provenance


def _verify_declaration(raw, pieces, target_revision, coverage):
    payload = decode_declaration(raw)
    if not isinstance(payload, dict) or payload.keys() != DECLARATION_FIELDS:
        raise ValueError('invalid reuse declaration fields')
    piece_name = _as_identifier(payload['piece'])
    if piece_name not in pieces:
        raise ValueError(f'declaration binds piece {piece_name} outside the selected coverage')
    piece = pieces[piece_name]
    if not isinstance(payload['old_issue'], str) or not isinstance(payload['old_revision'], str) \
            or not isinstance(payload['target_revision'], str) or not isinstance(payload['old_piece_sha256'], str):
        raise ValueError('invalid reuse declaration binding fields')
    if payload['survey'] != piece.survey:
        raise ValueError('declaration survey does not match the received piece')
    if payload['target_revision'] != target_revision:
        raise ValueError('declaration is bound to another target revision')
    if piece.revision_id == target_revision:
        raise ValueError(f'piece {piece_name} already matches the target revision and cannot be reused')
    if payload['old_revision'] != piece.revision_id:
        raise ValueError('declaration is not bound to the selected original revision')
    if payload['old_issue'] != piece.issue_id:
        raise ValueError('declaration is not bound to the selected original issue')
    if len(payload['old_piece_sha256']) != 64 or payload['old_piece_sha256'] != sha256(piece.raw).hexdigest():
        raise ValueError('declaration is bound to different original piece bytes')
    declared_coverage = payload['coverage']
    if not isinstance(declared_coverage, list) or not all(isinstance(name, str) for name in declared_coverage) \
            or tuple(sorted(declared_coverage)) != coverage:
        raise ValueError('declaration coverage does not match the selected piece set')

    if payload['starts'] != piece.starts:
        raise ValueError(f'declaration start table does not match piece {piece_name}')
    if any(route_id not in piece.routes for route_id in piece.starts.values()):
        raise ValueError('declaration start routes must exist on the original piece')

    inlet_routes = set()
    inlets = payload['inlets']
    if not isinstance(inlets, dict):
        raise ValueError('declaration inlets must be an object')
    for port, inlet in inlets.items():
        _as_identifier(port)
        if not isinstance(inlet, dict) or inlet.keys() != {'from_piece', 'route'}:
            raise ValueError('invalid declaration inlet record')
        source = _as_identifier(inlet['from_piece'])
        route_id = _as_identifier(inlet['route'])
        if source == piece_name or source not in coverage or route_id not in piece.routes:
            raise ValueError('declaration inlet points outside the selected coverage')
        inlet_routes.add(route_id)
    body_inlet_routes = {record['route'] for record in piece.incoming.values()}
    if inlet_routes != body_inlet_routes:
        raise ValueError('declaration inlets do not cover every inlet of the original piece')

    seams = payload['seams']
    if not isinstance(seams, dict):
        raise ValueError('declaration seams must be an object')
    seam_routes = set()
    for route_id, target in seams.items():
        route_id = _as_identifier(route_id)
        if not isinstance(target, dict) or target.keys() != {'piece', 'port', 'hops'}:
            raise ValueError('invalid declaration seam record')
        destination = _as_identifier(target['piece'])
        port = _as_identifier(target['port'])
        if type(target['hops']) is not int or target['hops'] < 1:
            raise ValueError('declaration seam hop count must be a positive integer')
        if destination == piece_name or destination not in coverage:
            raise ValueError('declaration seam leaves the selected coverage')
        route = piece.routes.get(route_id)
        if route is None or route['kind'] != 'seam':
            raise ValueError('declaration seam does not match an original seam route')
        if route['piece'] != destination or route['hops'] != target['hops']:
            raise ValueError('declaration seam disagrees with the original route evidence')
        seam_routes.add(route_id)
    body_seam_routes = {
        route_id for route_id, route in piece.routes.items() if route['kind'] == 'seam'
    }
    if seam_routes != body_seam_routes:
        raise ValueError('declaration seams do not cover every seam of the original piece')

    joins = payload['joins']
    if not isinstance(joins, list):
        raise ValueError('declaration joins must be an array')
    join_pairs = set()
    for row in joins:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('a declaration join needs two routes and two offsets')
        left, right, left_offset, right_offset = row
        left, right = _as_identifier(left), _as_identifier(right)
        if type(left_offset) is not int or type(right_offset) is not int \
                or left_offset < 0 or right_offset < 0:
            raise ValueError('declaration join offsets must be nonnegative integers')
        if left >= right or (left, right) in join_pairs or left not in piece.routes \
                or right not in piece.routes:
            raise ValueError('invalid or duplicate declaration join route pair')
        left_route, right_route = piece.routes[left], piece.routes[right]
        if left_route['kind'] != 'seam' or right_route['kind'] != 'seam' \
                or (left_route['piece'], left_route['port']) != (right_route['piece'], right_route['port']):
            raise ValueError('declaration joins must share one outgoing port')
        remaining = left_route['hops'] - left_offset
        if remaining <= 0 or remaining != right_route['hops'] - right_offset:
            raise ValueError('declaration join offsets disagree with the original routes')
        join_pairs.add((left, right))
    expected_joins = [list(row) for row in piece.joins]
    if joins != expected_joins:
        raise ValueError('declaration joins do not match the original piece joins')
    return piece_name, payload


def _resolve_reuse_handover(pieces, declarations, target_revision, start):
    coverage = tuple(sorted(next(iter(pieces.values())).coverage))
    if set(coverage) != set(pieces):
        raise ValueError('selected pieces do not match their declared coverage')
    reused = {}
    for raw in declarations:
        piece_name, payload = _verify_declaration(raw, pieces, target_revision, coverage)
        if piece_name in reused:
            raise ValueError(f'piece {piece_name} received more than one reuse declaration')
        reused[piece_name] = payload
    for name, piece in pieces.items():
        if piece.revision_id != target_revision and name not in reused:
            raise ValueError(f'cross-revision piece {name} lacks a reuse declaration')

    starts = {}
    routes = {}
    targets = {}
    joins = {}
    for name, piece in pieces.items():
        declaration = reused.get(name)
        start_table = piece.starts
        for public_point, route_id in start_table.items():
            if public_point in starts:
                raise ValueError(f'ambiguous public start {public_point}')
            starts[public_point] = (name, route_id)
        for route_id, route in piece.routes.items():
            key = name, route_id
            routes[key] = route
            if route['kind'] != 'seam':
                continue
            if declaration is not None:
                target_record = declaration['seams'][route_id]
                destination_name, port = target_record['piece'], target_record['port']
            else:
                destination_name, port = route['piece'], route['port']
            destination = pieces[destination_name]
            destination_declaration = reused.get(destination_name)
            if destination_declaration is not None:
                inlet = destination_declaration['inlets'].get(port)
            else:
                inlet = destination.incoming.get(port)
            if inlet is None or inlet['from_piece'] != name:
                raise ValueError(
                    f'unresolved seam from {name} to {destination_name} at {port}'
                )
            targets[key] = (destination_name, inlet['route'])
        for left, right, left_offset, right_offset in piece.joins:
            a, b = (name, left), (name, right)
            joins.setdefault(a, {})[b] = left_offset, right_offset
            joins.setdefault(b, {})[a] = right_offset, left_offset

    if not isinstance(start, str) or start not in starts:
        raise ValueError(f'unknown public start {start!r}')
    return ResolvedHandover(starts[start], routes, targets, joins), reused


def review_reuse(inventory, reports, survey, target_revision, receipt_ids, declarations, start):
    """Sign a target-revision determination from named originals and declarations."""
    if inventory.database.path != reports.database.path:
        raise ValueError('receipt inventory and reports must use the same center database')
    try:
        declaration_bytes = list(declarations)
    except TypeError as error:
        raise ValueError('declarations must be an iterable of bytes') from error
    if any(not isinstance(raw, bytes) for raw in declaration_bytes):
        raise ValueError('reuse declarations must be bytes')
    pieces, provenance = _select_reuse_pieces(inventory, survey, target_revision, receipt_ids)
    handover, reused = _resolve_reuse_handover(pieces, declaration_bytes, target_revision, start)
    outcome = trace_handover(handover)
    declaration_digests = {
        decode_declaration(raw)['piece']: digest_declaration(raw)
        for raw in declaration_bytes
    }
    selected = ReuseSelection(survey, target_revision, provenance)
    return publish_report(reports, selected, start, outcome, declaration_digests)
