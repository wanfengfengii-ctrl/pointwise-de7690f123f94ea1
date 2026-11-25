from hashlib import sha256

from issue.coverage import derive_coverage
from issue.declaration import encode_declaration
from issue.evidence import derive_piece_body
from receipt.validation import validate_piece
from survey.revision_store import FrozenRevision


# Public starts correspond by their public name. Real inlets correspond by the
# registration identity (source piece, target piece, target cell) inside one
# survey. Private cell names never leave the station; the declaration only
# carries the port numbering of the target revision.


def _anchor_identifiers(piece, coverage):
    """Map every public anchor of a piece to a stable cross-revision identity."""
    anchors = {}
    for name, cell in coverage.starts[piece].items():
        anchors[('start', name)] = cell
    for port, (source, cell) in coverage.inlets[piece].items():
        anchors[('inlet', source, piece, cell)] = cell
    return anchors


def _seam_destination(topology, coverage, terminal):
    """Resolve a seam terminal to its real inlet (source, target piece, cell)."""
    target_piece = terminal['piece']
    port = terminal['port']
    source, cell = coverage.inlets[target_piece][port]
    return source, target_piece, cell


def _join_index(body, mapping):
    index = {}
    for left, right, left_offset, right_offset in body['joins']:
        key = tuple(sorted((mapping[left], mapping[right])))
        index[key] = (left_offset, right_offset)
    return index


def build_reuse_declaration(old_revision: FrozenRevision, target_revision: FrozenRevision,
                            piece, old_raw, old_issue_id):
    old_topology = old_revision.topology
    target_topology = target_revision.topology
    if old_topology.survey != target_topology.survey:
        raise ValueError('reuse declarations only apply within one survey')
    if tuple(old_topology.pieces) != tuple(target_topology.pieces):
        raise ValueError('the declared piece set must stay identical')
    if piece not in old_topology.pieces:
        raise ValueError(f'piece {piece!r} is outside the frozen coverage')

    old_coverage = derive_coverage(old_revision)
    target_coverage = derive_coverage(target_revision)
    old_body = derive_piece_body(old_revision, old_coverage, piece)
    target_body = derive_piece_body(target_revision, target_coverage, piece)

    old_anchors = _anchor_identifiers(piece, old_coverage)
    target_anchors = _anchor_identifiers(piece, target_coverage)
    if set(old_anchors) != set(target_anchors):
        raise ValueError(f'piece {piece}: public starts and real inlets do not correspond')

    # Old route id -> target route id, keyed by the shared anchor identity.
    route_mapping = {}
    for identity in sorted(old_anchors):
        if identity[0] == 'start':
            old_route = old_body['starts'][identity[1]]
            target_route = target_body['starts'][identity[1]]
        else:
            source, target_piece, cell = identity[1:]
            old_port = _port_for_inlet(old_coverage, piece, source, cell)
            target_port = _port_for_inlet(target_coverage, piece, source, cell)
            old_route = old_body['incoming'][old_port]['route']
            target_route = target_body['incoming'][target_port]['route']
        if old_route in route_mapping:
            raise ValueError(f'piece {piece}: inlet anchors collapsed onto one route')
        route_mapping[old_route] = target_route
    if len(route_mapping) != len(old_body['routes']) or set(route_mapping.values()) != set(target_body['routes']):
        raise ValueError(f'piece {piece}: routes do not correspond one to one')

    starts = {name: old_body['starts'][name] for name in sorted(old_body['starts'])}
    inlets = {}
    seam_map = {}
    for identity in sorted(old_anchors):
        if identity[0] != 'inlet':
            continue
        source, target_piece, cell = identity[1:]
        target_port = _port_for_inlet(target_coverage, piece, source, cell)
        old_port = _port_for_inlet(old_coverage, piece, source, cell)
        old_route = old_body['incoming'][old_port]['route']
        inlets[target_port] = {'from_piece': source, 'route': old_route}

    # Every terminal must keep its business evidence under the target revision.
    for old_route, target_route in sorted(route_mapping.items()):
        old_terminal = old_body['routes'][old_route]
        target_terminal = target_body['routes'][target_route]
        if old_terminal['kind'] != target_terminal['kind']:
            raise ValueError(f'piece {piece}: route {old_route} changed its terminal kind')
        kind = old_terminal['kind']
        if kind == 'outlet':
            if (old_terminal['outlet'], old_terminal['hops']) != (
                target_terminal['outlet'], target_terminal['hops']
            ):
                raise ValueError(f'piece {piece}: outlet evidence changed for {old_route}')
        elif kind == 'loop':
            if (old_terminal['entry_hops'], old_terminal['loop_length']) != (
                target_terminal['entry_hops'], target_terminal['loop_length']
            ):
                raise ValueError(f'piece {piece}: loop evidence changed for {old_route}')
        else:
            if old_terminal['hops'] != target_terminal['hops']:
                raise ValueError(f'piece {piece}: seam hop count changed for {old_route}')
            old_destination = _seam_destination(old_topology, old_coverage, old_terminal)
            target_destination = _seam_destination(target_topology, target_coverage, target_terminal)
            if old_destination != target_destination:
                raise ValueError(f'piece {piece}: seam {old_route} no longer reaches the same real inlet')
            _, destination_piece, _ = target_destination
            seam_map[old_route] = {
                'piece': destination_piece,
                'port': target_terminal['port'],
                'hops': old_terminal['hops'],
            }

    # First-meeting joins must survive with the same two-side offsets.
    old_joins = _join_index(old_body, {route: route for route in old_body['routes']})
    target_joins = _join_index(target_body, route_mapping)
    if set(old_joins) != set(target_joins):
        raise ValueError(f'piece {piece}: first join presence changed')
    for key, offsets in old_joins.items():
        if offsets != target_joins[key]:
            raise ValueError(f'piece {piece}: join offsets changed for {key}')

    joins = [
        [left, right, left_offset, right_offset]
        for (left, right), (left_offset, right_offset) in sorted(old_joins.items())
    ]
    payload = {
        'survey': old_topology.survey,
        'piece': piece,
        'old_issue': old_issue_id,
        'old_piece_sha256': sha256(old_raw).hexdigest(),
        'old_revision': old_revision.revision_id,
        'target_revision': target_revision.revision_id,
        'coverage': list(target_topology.pieces),
        'starts': starts,
        'inlets': inlets,
        'seams': seam_map,
        'joins': joins,
    }
    return payload


def _port_for_inlet(coverage, piece, source, cell):
    for port, (incoming_source, incoming_cell) in coverage.inlets[piece].items():
        if incoming_source == source and incoming_cell == cell:
            return port
    raise ValueError('inlet identity missing from target coverage')


def compatibility_for(revisions, catalog, old_issue_id, target_revision):
    """Issue a reuse declaration binding one fixed piece to another revision."""
    issued = catalog.load(old_issue_id)
    verified = validate_piece(issued.raw)
    if not isinstance(target_revision, str) or not target_revision:
        raise ValueError('expected a target revision ID')
    old_revision = revisions.load(verified.revision_id)
    target = revisions.load(target_revision)
    if old_revision.revision_id == target_revision:
        raise ValueError('a reuse declaration needs a different target revision')
    if old_revision.topology.survey != target.topology.survey:
        raise ValueError('the target revision belongs to another survey')
    payload = build_reuse_declaration(
        old_revision, target, verified.piece, issued.raw, old_issue_id
    )
    return encode_declaration(payload)
