from dataclasses import dataclass

from receipt.coverage import check_coverage
from receipt.validation import VerifiedPiece


@dataclass(frozen=True)
class SelectedPieces:
    survey: str
    revision_id: str
    pieces: dict[str, VerifiedPiece]
    provenance: tuple[tuple[str, int], ...]


def select_pieces(inventory, survey, revision_id, receipt_ids):
    if not isinstance(survey, str) or not survey or not isinstance(revision_id, str) or not revision_id:
        raise ValueError('expected a survey and revision ID')
    try:
        ids = iter(receipt_ids)
    except TypeError as error:
        raise ValueError('receipt IDs must be an iterable of integers') from error

    received = {}
    for receipt_id in ids:
        if type(receipt_id) is not int:
            raise ValueError('receipt ID must be an integer')
        if receipt_id in received:
            continue
        piece = inventory.load(receipt_id)
        if (piece.survey, piece.revision_id) != (survey, revision_id):
            raise ValueError(f'receipt {receipt_id} is outside the requested survey revision')
        received[receipt_id] = piece

    by_piece = check_coverage(received.items())
    names = sorted(by_piece)
    return SelectedPieces(
        survey,
        revision_id,
        {name: by_piece[name][1] for name in names},
        tuple((name, by_piece[name][0]) for name in names),
    )
