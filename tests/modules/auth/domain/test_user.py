"""TSK-008 RED: User aggregate, UserEmail/UserId VOs, password hashing, sessions.

Pure domain, strict self-contained validation. Written BEFORE production code.
"""

import pytest

from src.modules.auth.domain.entities import AuthSession, User
from src.modules.auth.domain.exceptions import UserValidationError
from src.modules.auth.domain.security import hash_password, verify_password
from src.modules.auth.domain.value_objects import UserEmail, UserId


class TestUserEmail:
    def test_accepts_valid_and_normalizes(self) -> None:
        assert UserEmail("  Pro@Example.COM ").value == "pro@example.com"

    @pytest.mark.parametrize(
        "raw", ["", "   ", "no-at-sign", "a@b", "a@" * 90 + "x.com", "a b@c.com"]
    )
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(UserValidationError):
            UserEmail(raw)


class TestUserId:
    def test_generates_unique_ids(self) -> None:
        assert UserId.generate() != UserId.generate()

    def test_roundtrip_from_string(self) -> None:
        uid = UserId.generate()
        assert UserId(str(uid)) == uid

    def test_rejects_invalid(self) -> None:
        with pytest.raises(UserValidationError):
            UserId("not-a-uuid")


class TestPasswordHashing:
    def test_hash_is_never_plaintext(self) -> None:
        hashed = hash_password("s3cret-pass")
        assert hashed != "s3cret-pass"
        assert "s3cret-pass" not in hashed

    def test_hash_uses_random_salt(self) -> None:
        assert hash_password("same-password") != hash_password("same-password")

    def test_verify_accepts_correct_password(self) -> None:
        assert verify_password("s3cret-pass", hash_password("s3cret-pass")) is True

    def test_verify_rejects_wrong_password(self) -> None:
        assert verify_password("wrong-pass", hash_password("s3cret-pass")) is False

    @pytest.mark.parametrize("raw", ["", "   ", "short", "1234567"])
    def test_rejects_weak_password(self, raw: str) -> None:
        with pytest.raises(UserValidationError):
            hash_password(raw)


class TestUser:
    def test_creates_user_with_hashed_password(self) -> None:
        user = User(
            id=UserId.generate(),
            email=UserEmail("pro@example.com"),
            password_hash=hash_password("s3cret-pass"),
        )
        assert user.email == UserEmail("pro@example.com")
        assert user.password_hash != "s3cret-pass"
        assert verify_password("s3cret-pass", user.password_hash) is True

    def test_user_id_is_owner_identity(self) -> None:
        uid = UserId.generate()
        user = User(
            id=uid,
            email=UserEmail("pro@example.com"),
            password_hash=hash_password("s3cret-pass"),
        )
        assert str(user.id) == str(uid)


class TestAuthSession:
    def test_tokens_are_opaque_and_unique(self) -> None:
        first = AuthSession.issue(str(UserId.generate()))
        second = AuthSession.issue(first.user_id)
        assert first.token
        assert second.token
        assert first.token != second.token
        assert first.user_id not in first.token  # opaque: carries no identity data
        assert first.user_id == second.user_id

    def test_rejects_empty_user_id(self) -> None:
        with pytest.raises(UserValidationError):
            AuthSession.issue("   ")
