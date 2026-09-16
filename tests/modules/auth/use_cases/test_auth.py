"""TSK-008 RED: RegisterUser + AuthenticateUser use cases.

Depends only on the IUserRepository port (DIP) via an in-memory fake.
Written BEFORE production code.
"""

import pytest

from src.modules.auth.domain.entities import User
from src.modules.auth.domain.exceptions import (
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserValidationError,
)
from src.modules.auth.domain.repository_interfaces import IUserRepository
from src.modules.auth.domain.value_objects import UserEmail, UserId
from src.modules.auth.use_cases.authenticate_user import AuthenticateUser
from src.modules.auth.use_cases.register_user import RegisterUser


class InMemoryUserRepository(IUserRepository):
    """Test-only fake of the IUserRepository port."""

    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}

    def save(self, user: User) -> None:
        self._by_email[user.email.value] = user

    def find_by_email(self, email: UserEmail) -> User | None:
        return self._by_email.get(email.value)


def _repo_with_user(
    email: str = "pro@example.com", password: str = "s3cret-pass"
) -> InMemoryUserRepository:
    repo = InMemoryUserRepository()
    RegisterUser(repo).execute(email=email, password=password)
    return repo


class TestRegisterUser:
    def test_registers_user_success(self) -> None:
        repo = InMemoryUserRepository()
        user = RegisterUser(repo).execute(
            email="  Pro@Example.COM ", password="s3cret-pass"
        )
        assert user.email == UserEmail("pro@example.com")
        assert user.password_hash != "s3cret-pass"
        stored = repo.find_by_email(UserEmail("pro@example.com"))
        assert stored == user

    def test_rejects_duplicate_email(self) -> None:
        repo = _repo_with_user()
        with pytest.raises(UserAlreadyExistsError):
            RegisterUser(repo).execute(
                email="PRO@example.com", password="another-pass"
            )

    @pytest.mark.parametrize("raw", ["", "   ", "no-at-sign", "a@b"])
    def test_rejects_invalid_email(self, raw: str) -> None:
        with pytest.raises(UserValidationError):
            RegisterUser(InMemoryUserRepository()).execute(
                email=raw, password="s3cret-pass"
            )

    @pytest.mark.parametrize("raw", ["", "   ", "short"])
    def test_rejects_weak_password(self, raw: str) -> None:
        with pytest.raises(UserValidationError):
            RegisterUser(InMemoryUserRepository()).execute(
                email="pro@example.com", password=raw
            )

    def test_user_id_is_generated_per_registration(self) -> None:
        repo = InMemoryUserRepository()
        first = RegisterUser(repo).execute(
            email="a@example.com", password="s3cret-pass"
        )
        second = RegisterUser(repo).execute(
            email="b@example.com", password="s3cret-pass"
        )
        assert first.id != second.id
        assert isinstance(first.id, UserId)


class TestAuthenticateUser:
    def test_login_success_returns_session(self) -> None:
        repo = _repo_with_user()
        session = AuthenticateUser(repo).execute(
            email="pro@example.com", password="s3cret-pass"
        )
        owner = repo.find_by_email(UserEmail("pro@example.com"))
        assert owner is not None
        assert session.user_id == str(owner.id)
        assert session.token

    def test_login_is_case_insensitive_on_email(self) -> None:
        repo = _repo_with_user()
        session = AuthenticateUser(repo).execute(
            email="PRO@Example.COM", password="s3cret-pass"
        )
        assert session.token

    def test_wrong_password_raises_generic_error(self) -> None:
        repo = _repo_with_user()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            AuthenticateUser(repo).execute(
                email="pro@example.com", password="wrong-pass"
            )
        assert str(exc_info.value) == InvalidCredentialsError.GENERIC_MESSAGE

    def test_unknown_email_raises_same_generic_error(self) -> None:
        repo = _repo_with_user()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            AuthenticateUser(repo).execute(
                email="ghost@example.com", password="s3cret-pass"
            )
        # Same message as wrong-password: no user enumeration.
        assert str(exc_info.value) == InvalidCredentialsError.GENERIC_MESSAGE

    def test_malformed_email_raises_same_generic_error(self) -> None:
        repo = _repo_with_user()
        with pytest.raises(InvalidCredentialsError) as exc_info:
            AuthenticateUser(repo).execute(email="not-an-email", password="s3cret-pass")
        # Unregistered/malformed emails are indistinguishable: no enumeration.
        assert str(exc_info.value) == InvalidCredentialsError.GENERIC_MESSAGE

    def test_each_login_issues_unique_token(self) -> None:
        repo = _repo_with_user()
        login = AuthenticateUser(repo)
        first = login.execute(email="pro@example.com", password="s3cret-pass")
        second = login.execute(email="pro@example.com", password="s3cret-pass")
        assert first.token != second.token
