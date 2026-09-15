"""ChronoLog appointments domain exceptions (pure, stdlib only)."""


class AppointmentValidationError(ValueError):
    """Raised when an Appointment or SessionNotes invariant is violated."""
