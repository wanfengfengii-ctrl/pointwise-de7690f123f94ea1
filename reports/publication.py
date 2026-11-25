from reports.format import format_report
from reports.receipts import make_first_receipt
from reports.store import ReportBundle


def publish_report(store, selected, start, outcome, declaration_digests=None):
    with store.transaction() as connection:
        report_id = store.reserve_report_id(connection)
        if declaration_digests is None:
            report = format_report(report_id, selected.survey, selected.revision_id, start, outcome)
        else:
            report = format_report(
                report_id, selected.survey, selected.revision_id, start, outcome,
                sources=selected.provenance, declaration_digests=declaration_digests,
            )
        first_receipt = make_first_receipt(
            report_id, report, selected.provenance, declaration_digests
        )
        bundle = ReportBundle(report_id, report, selected.provenance, first_receipt)
        store.save_bundle(connection, bundle)
    return bundle
