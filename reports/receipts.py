from hashlib import sha256
import json


def make_first_receipt(report_id, report, provenance, declaration_digests=None):
    document = {
        'report_id': report_id,
        'report_sha256': sha256(report).hexdigest(),
        'sources': dict(provenance),
    }
    if declaration_digests is not None:
        document['reuse_declarations'] = dict(declaration_digests)
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
