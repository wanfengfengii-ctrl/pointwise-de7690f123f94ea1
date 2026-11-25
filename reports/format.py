import json

from review.outcomes import LoopOutcome, OutletOutcome


def format_report(report_id, survey, revision_id, start, outcome: OutletOutcome | LoopOutcome):
    document = {
        'report_id': report_id,
        'survey': survey,
        'revision': revision_id,
        'start': start,
        'outcome': outcome.as_record(),
    }
    return json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
