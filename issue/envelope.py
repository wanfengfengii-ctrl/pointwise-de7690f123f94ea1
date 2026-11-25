import hashlib
from hmac import compare_digest
import json


V1_VERSION = 1


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f'duplicate JSON field {name!r}')
        result[name] = value
    return result


def _invalid_constant(value):
    raise ValueError(f'non-JSON constant {value}')


def _parse(text):
    return json.loads(text, object_pairs_hook=_unique_fields, parse_constant=_invalid_constant)


def _valid_issue_id(issue_id):
    return (
        isinstance(issue_id, str) and bool(issue_id) and issue_id.isascii()
        and all(char.isalnum() or char in '-_' for char in issue_id)
    )


def encode_envelope(issue_id, body):
    if not _valid_issue_id(issue_id) or not isinstance(body, dict):
        raise ValueError('expected a V1 issue identity and body object')
    text = _json(body)
    return _json({
        'version': V1_VERSION,
        'issue_id': issue_id,
        'body': text,
        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
    }).encode('utf-8')


def decode_envelope(raw):
    if not isinstance(raw, bytes):
        raise ValueError('a fixed piece must be bytes')
    try:
        envelope = _parse(raw.decode('utf-8'))
        if not isinstance(envelope, dict) or envelope.keys() != {'version', 'issue_id', 'body', 'sha256'}:
            raise ValueError('invalid envelope fields')
        if type(envelope['version']) is not int or envelope['version'] != V1_VERSION:
            raise ValueError('unsupported envelope version')
        issue_id, text, checksum = envelope['issue_id'], envelope['body'], envelope['sha256']
        if not _valid_issue_id(issue_id) or not isinstance(text, str):
            raise ValueError('invalid issue identity or body')
        if not isinstance(checksum, str) or len(checksum) != 64 or not checksum.isascii():
            raise ValueError('invalid body checksum')
        actual = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if not compare_digest(checksum, actual):
            raise ValueError('body checksum mismatch')
        body = _parse(text)
        if not isinstance(body, dict):
            raise ValueError('body must be a JSON object')
    except (UnicodeError, RecursionError) as error:
        raise ValueError('invalid V1 JSON encoding') from error
    return issue_id, body
