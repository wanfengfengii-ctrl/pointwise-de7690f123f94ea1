from reports.format import format_report
from reports.receipts import make_first_receipt
from reports.store import ReportBundle


def publish_report(store, selected, start, outcome):
    with store.transaction() as connection:
        report_id = store.reserve_report_id(connection)
        report = format_report(report_id, selected.survey, selected.revision_id, start, outcome)
        first_receipt = make_first_receipt(report_id, report, selected.provenance)
        bundle = ReportBundle(report_id, report, selected.provenance, first_receipt)
        store.save_bundle(connection, bundle)
    return bundle
