def check_coverage(received):
    """Index a complete received set by its declared piece names."""
    declared = None
    by_piece = {}
    for receipt_id, piece in received:
        if declared is None:
            declared = piece.coverage
        if piece.coverage != declared:
            raise ValueError('inconsistent coverage declarations')
        if piece.piece in by_piece:
            raise ValueError(f'ambiguous receipts for piece {piece.piece}')
        by_piece[piece.piece] = (receipt_id, piece)
    if declared is None:
        raise ValueError('no received pieces selected')
    missing = set(declared) - by_piece.keys()
    extra = by_piece.keys() - set(declared)
    if missing or extra:
        raise ValueError(f'incomplete coverage: missing {sorted(missing)}, extra {sorted(extra)}')
    return by_piece
