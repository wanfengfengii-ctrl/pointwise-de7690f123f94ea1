from receipt.selection import select_pieces
from reports.publication import publish_report
from review.ports import resolve_ports
from review.reuse import review_reuse
from review.trace import trace_handover

__all__ = ['review', 'review_reuse']


def review(inventory, reports, survey, revision_id, receipt_ids, start):
    """Sign a determination made solely from the named received pieces."""
    if inventory.database.path != reports.database.path:
        raise ValueError('receipt inventory and reports must use the same center database')
    selected = select_pieces(inventory, survey, revision_id, receipt_ids)
    handover = resolve_ports(selected, start)
    outcome = trace_handover(handover)
    return publish_report(reports, selected, start, outcome)
