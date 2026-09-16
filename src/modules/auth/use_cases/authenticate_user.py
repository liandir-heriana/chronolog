"""ChronoLog AuthenticateUser use case (depends only on IUserRepository port)."""

from __future__ import annotations

from src.modules.auth.domain.entities import AuthSession
from src.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    UserValidationError,
)
from src.modules.auth.domain.repository_interfaces import IUserRepository
from src.modules.auth.domain.security import verify_password
from src.modules.auth.domain.value_objects import UserEmail


class AuthenticateUser:
    """Login: verify hash, issue an opaque session token on success.

    Every failure (unknown email, malformed email, wrong password) raises
    the same generic :class:`InvalidCredentialsError` to avoid user
    enumeration.
    """

    def __init__(self, users: IUserRepository) -> None:
        self._users = users

    def execute(self, *, email: str, password: str) -> AuthSession:
        """Verify credentials and return a fresh unique-token session."""
        try:
            address = UserEmail(email)
        except UserValidationError:
            raise InvalidCredentialsError() from None
        user = self._users.find_by_email(address)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        return AuthSession.issue(str(user.id))
