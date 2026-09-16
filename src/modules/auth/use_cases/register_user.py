"""ChronoLog RegisterUser use case (depends only on the IUserRepository port)."""

from __future__ import annotations

from src.modules.auth.domain.entities import User
from src.modules.auth.domain.exceptions import UserAlreadyExistsError
from src.modules.auth.domain.repository_interfaces import IUserRepository
from src.modules.auth.domain.security import hash_password
from src.modules.auth.domain.value_objects import UserEmail, UserId


class RegisterUser:
    """Register a new account: validate email, reject duplicates, hash password."""

    def __init__(self, users: IUserRepository) -> None:
        self._users = users

    def execute(self, *, email: str, password: str) -> User:
        """Create, persist, and return the new user (email normalized)."""
        address = UserEmail(email)
        if self._users.find_by_email(address) is not None:
            raise UserAlreadyExistsError(f"Email already registered: {address.value!r}")
        user = User(
            id=UserId.generate(),
            email=address,
            password_hash=hash_password(password),
        )
        self._users.save(user)
        return user
