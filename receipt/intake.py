from receipt.validation import validate_piece


def receive(inventory, raw):
    """Validate a V1 piece and return its fixed receipt ID."""
    return inventory.register(validate_piece(raw))
