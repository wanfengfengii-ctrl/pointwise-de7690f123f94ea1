from survey.intake import parse_survey
from survey.topology import validate_topology


def freeze(store, registration):
    """Return a new revision ID after the entire work draft passes validation."""
    draft = parse_survey(registration)
    return store.save(validate_topology(draft))
