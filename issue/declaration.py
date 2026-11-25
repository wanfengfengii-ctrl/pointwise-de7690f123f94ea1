import hashlib
from hmac import compare_digest
import json


# Reuse declarations reuse the V1 transport integrity boundary with their own
# version number so a V1 piece can never be mistaken for a declaration.
DECLARATION_VERSION = 2


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


def encode_declaration(payload):
    if not isinstance(payload, dict):
        raise ValueError('a reuse declaration needs a payload object')
    text = _json(payload)
    return _json({
        'version': DECLARATION_VERSION,
        'body': text,
        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
    }).encode('utf-8')


def decode_declaration(raw):
    if not isinstance(raw, bytes):
        raise ValueError('a reuse declaration must be bytes')
    try:
        envelope = _parse(raw.decode('utf-8'))
        if not isinstance(envelope, dict) or envelope.keys() != {'version', 'body', 'sha256'}:
            raise ValueError('invalid declaration envelope fields')
        if type(envelope['version']) is not int or envelope['version'] != DECLARATION_VERSION:
            raise ValueError('unsupported declaration version')
        text, checksum = envelope['body'], envelope['sha256']
        if not isinstance(text, str):
            raise ValueError('invalid declaration body')
        if not isinstance(checksum, str) or len(checksum) != 64 or not checksum.isascii():
            raise ValueError('invalid declaration checksum')
        actual = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if not compare_digest(checksum, actual):
            raise ValueError('declaration checksum mismatch')
        payload = _parse(text)
        if not isinstance(payload, dict):
            raise ValueError('declaration body must be a JSON object')
    except (UnicodeError, RecursionError) as error:
        raise ValueError('invalid declaration JSON encoding') from error
    return payload


def digest_declaration(raw):
    """SHA-256 of the exact declaration bytes, as recorded in reports."""
    return hashlib.sha256(raw).hexdigest()
