from hashlib import sha256
import json


def make_first_receipt(report_id, report, provenance):
    document = {
        'report_id': report_id,
        'report_sha256': sha256(report).hexdigest(),
        'sources': dict(provenance),
    }
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
