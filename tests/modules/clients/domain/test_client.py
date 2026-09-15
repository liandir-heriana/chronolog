"""TSK-005 RED: Client aggregate root + Email/Phone/ClientId value objects.

Pure domain, strict self-contained validation. Written BEFORE production code.
"""

import pytest

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.exceptions import ClientValidationError
from src.modules.clients.domain.value_objects import ClientId, Email, Phone


class TestEmail:
    def test_accepts_valid_and_normalizes(self) -> None:
        assert Email("  Pro@Example.COM ").value == "pro@example.com"

    @pytest.mark.parametrize(
        "raw", ["", "   ", "no-at-sign", "a@b", "a@" * 90 + "x.com", "a b@c.com"]
    )
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ClientValidationError):
            Email(raw)


class TestPhone:
    def test_accepts_valid_and_normalizes(self) -> None:
        assert Phone("+34 600-123 456").value == "+34600123456"
        assert Phone("600123456").value == "600123456"

    @pytest.mark.parametrize(
        "raw", ["", "   ", "123456", "+1234567890123456", "abc1234567", "++34600123"]
    )
    def test_rejects_invalid(self, raw: str) -> None:
        with pytest.raises(ClientValidationError):
            Phone(raw)


class TestClientId:
    def test_generates_unique_ids(self) -> None:
        assert ClientId.generate() != ClientId.generate()

    def test_roundtrip_from_string(self) -> None:
        cid = ClientId.generate()
        assert ClientId(str(cid)) == cid

    def test_rejects_invalid(self) -> None:
        with pytest.raises(ClientValidationError):
            ClientId("not-a-uuid")


class TestClient:
    def test_creates_valid_client(self) -> None:
        client = Client(
            id=ClientId.generate(),
            user_id="user-1",
            name="Ada Lovelace",
            email=Email("ada@example.com"),
            phone=Phone("+34600123456"),
        )
        assert client.user_id == "user-1"
        assert client.name == "Ada Lovelace"
        assert client.phone is not None

    def test_phone_is_optional(self) -> None:
        client = Client(
            id=ClientId.generate(),
            user_id="user-1",
            name="Ada",
            email=Email("ada@example.com"),
        )
        assert client.phone is None

    @pytest.mark.parametrize("user_id", ["", "   "])
    def test_rejects_empty_user_id(self, user_id: str) -> None:
        with pytest.raises(ClientValidationError):
            Client(
                id=ClientId.generate(),
                user_id=user_id,
                name="Ada",
                email=Email("ada@example.com"),
            )

    @pytest.mark.parametrize("name", ["", "   ", "x" * 101])
    def test_rejects_invalid_name(self, name: str) -> None:
        with pytest.raises(ClientValidationError):
            Client(
                id=ClientId.generate(),
                user_id="user-1",
                name=name,
                email=Email("ada@example.com"),
            )

    def test_update_contact_revalidates(self) -> None:
        client = Client(
            id=ClientId.generate(),
            user_id="user-1",
            name="Ada",
            email=Email("ada@example.com"),
        )
        client.update_contact(name="  Grace Hopper ", email=Email("grace@example.com"))
        assert client.name == "Grace Hopper"
        with pytest.raises(ClientValidationError):
            client.update_contact(name="   ")

    def test_update_and_clear_phone(self) -> None:
        client = Client(
            id=ClientId.generate(),
            user_id="user-1",
            name="Ada",
            email=Email("ada@example.com"),
        )
        client.update_contact(phone=Phone("+34600123456"))
        assert client.phone == Phone("+34600123456")
        client.update_contact(clear_phone=True)
        assert client.phone is None
