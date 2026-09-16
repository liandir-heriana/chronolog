"""ChronoLog auth domain exceptions (pure, stdlib only)."""


class UserValidationError(ValueError):
    """Raised when a User aggregate or value object invariant is violated."""


class UserAlreadyExistsError(ValueError):
    """Raised when registering an email that is already taken."""


class InvalidCredentialsError(ValueError):
    """Generic login failure (wrong password or unknown email).

    A single message for every failure mode prevents user enumeration:
    callers must never reveal whether the email exists.
    """

    GENERIC_MESSAGE = "Invalid email or password"

    def __init__(self, message: str = GENERIC_MESSAGE) -> None:
        super().__init__(message)
