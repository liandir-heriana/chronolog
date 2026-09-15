"""ChronoLog clients domain exceptions (pure, stdlib only)."""


class ClientValidationError(ValueError):
    """Raised when a Client aggregate or value object invariant is violated."""
