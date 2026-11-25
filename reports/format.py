import json

from review.outcomes import LoopOutcome, OutletOutcome


def format_report(report_id, survey, revision_id, start, outcome: OutletOutcome | LoopOutcome,
                  sources=None, declaration_digests=None):
    document = {
        'report_id': report_id,
        'survey': survey,
        'revision': revision_id,
        'start': start,
        'outcome': outcome.as_record(),
    }
    if sources is not None:
        document['sources'] = dict(sources)
        document['reuse_declarations'] = dict(declaration_digests or {})
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
