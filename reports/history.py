def read(store, report_id):
    """Return the stored report, exact received sources and first receipt."""
    return store.load_bundle(report_id)
