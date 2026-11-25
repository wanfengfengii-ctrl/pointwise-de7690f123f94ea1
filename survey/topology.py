from dataclasses import dataclass

from survey.intake import SurveyDraft


@dataclass(frozen=True)
class ValidatedTopology:
    survey: str
    pieces: tuple[str, ...]
    cells: dict[str, str]
    missing: dict[str, str]
    successors: dict[str, str]
    starts: dict[str, str]
    outlets: dict[str, str]


def _named_cells(rows, cells, kind):
    named = {}
    for name, cell in rows:
        if name in named:
            raise ValueError(f'duplicate {kind} name {name}')
        if cell not in cells:
            raise ValueError(f'{kind} {name} must name a valid cell')
        named[name] = cell
    return named


def validate_topology(draft: SurveyDraft):
    pieces = set(draft.pieces)
    if not pieces or len(pieces) != len(draft.pieces):
        raise ValueError('declare a nonempty set of distinct pieces')
    cells = {}
    missing = {}
    for cell, piece, present in draft.cells:
        if piece not in pieces:
            raise ValueError(f'undeclared piece {piece} for cell {cell}')
        if cell in cells or cell in missing:
            raise ValueError(f'duplicate cell {cell}')
        registry = cells if present else missing
        registry[cell] = piece

    starts = _named_cells(draft.starts, cells, 'start')
    outlet_points = _named_cells(draft.outlets, cells, 'outlet')
    outlets = {cell: name for name, cell in outlet_points.items()}
    if len(outlets) != len(outlet_points):
        raise ValueError('a cell cannot carry multiple outlet names')

    successors = {}
    for cell, target in draft.links:
        if cell not in cells or target not in cells:
            raise ValueError(f'link {cell} to {target} must connect valid cells')
        if cell in successors:
            raise ValueError(f'multiple successors registered for {cell}')
        if cell in outlets:
            raise ValueError(f'outlet {outlets[cell]} cannot have a successor')
        successors[cell] = target

    unregistered = cells.keys() - successors.keys() - outlets.keys()
    if unregistered:
        raise ValueError(f'no successor or registered outlet for {min(unregistered)}')
    return ValidatedTopology(
        draft.survey, tuple(sorted(pieces)), cells, missing, successors, starts, outlets
    )
