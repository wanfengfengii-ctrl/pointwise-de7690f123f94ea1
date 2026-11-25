from dataclasses import dataclass


@dataclass
class SurveyDraft:
    survey: str
    pieces: list[str]
    cells: list[tuple[str, str, bool]]
    links: list[tuple[str, str]]
    starts: list[tuple[str, str]]
    outlets: list[tuple[str, str]]


def _identifier(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('expected a nonempty identifier')
    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError('invalid character in identifier')
    return value


def _rows(data, field, width):
    records = data[field]
    if not isinstance(records, list):
        raise ValueError(f'{field} must be an array of records')
    for record in records:
        if not isinstance(record, (tuple, list)) or len(record) != width:
            raise ValueError(f'{field} record must contain {width} fields')
        yield record


def _cell_records(data):
    for cell, piece, present in _rows(data, 'cells', 3):
        if type(present) is not bool:
            raise ValueError('cell presence must be a boolean')
        yield _identifier(cell), _identifier(piece), present


def parse_survey(data):
    if isinstance(data, SurveyDraft):
        data = vars(data)
    fields = {'survey', 'pieces', 'cells', 'links', 'starts', 'outlets'}
    if not isinstance(data, dict) or data.keys() != fields:
        raise ValueError('expected a survey registration with all six fields')
    if not isinstance(data['pieces'], list):
        raise ValueError('pieces must be an array')
    return SurveyDraft(
        survey=_identifier(data['survey']),
        pieces=[_identifier(piece) for piece in data['pieces']],
        cells=list(_cell_records(data)),
        links=[(_identifier(cell), _identifier(target)) for cell, target in _rows(data, 'links', 2)],
        starts=[(_identifier(name), _identifier(cell)) for name, cell in _rows(data, 'starts', 2)],
        outlets=[(_identifier(name), _identifier(cell)) for name, cell in _rows(data, 'outlets', 2)],
    )
