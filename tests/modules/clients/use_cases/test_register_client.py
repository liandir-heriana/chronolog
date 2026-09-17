"""TSK-016 RED: RegisterClient use case (Clients tab needs a use-case boundary).

Written BEFORE production code — must FAIL on collection until
`src/modules/clients/use_cases/register_client.py` exists.

Rationale: TSK-005..011 left no client-creation use-case; the Gradio Clients
tab must call a use-case with authenticated `user_id` (never build rows in
the UI, never touch adapters). MUST scope (proposal: Client Registration).
"""

import pytest

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.exceptions import ClientValidationError
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId
from src.modules.clients.use_cases.register_client import RegisterClient


class InMemoryClientRepository(IClientRepository):
    """Test-only fake of the IClientRepository port."""

    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[f"{client.user_id}:{client.id.value}"] = client

    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        return self._store.get(f"{user_id}:{client_id.value}")

    def list_by_user_id(self, user_id: str) -> list[Client]:
        return [c for c in self._store.values() if c.user_id == user_id]


def test_registers_client_for_owner() -> None:
    repo = InMemoryClientRepository()
    client = RegisterClient(repo).execute(
        user_id="user-1",
        name="  Alice Smith ",
        email="Alice@Example.COM",
        phone="+34 600 111 222",
    )
    assert client.user_id == "user-1"
    assert client.name == "Alice Smith"
    assert client.email.value == "alice@example.com"
    assert client.phone is not None
    assert repo.find_by_id_and_user_id(client.id, "user-1") == client


def test_registers_client_without_phone() -> None:
    repo = InMemoryClientRepository()
    client = RegisterClient(repo).execute(
        user_id="user-1", name="No Phone", email="nophone@example.com"
    )
    assert client.phone is None


def test_ids_are_unique_per_registration() -> None:
    repo = InMemoryClientRepository()
    use_case = RegisterClient(repo)
    first = use_case.execute(user_id="u", name="A", email="a@example.com")
    second = use_case.execute(user_id="u", name="B", email="b@example.com")
    assert first.id != second.id


@pytest.mark.parametrize("user_id", ["", "   "])
def test_rejects_empty_owner(user_id: str) -> None:
    with pytest.raises(ClientValidationError):
        RegisterClient(InMemoryClientRepository()).execute(
            user_id=user_id, name="Alice", email="alice@example.com"
        )


@pytest.mark.parametrize("name", ["", "   "])
def test_rejects_blank_name(name: str) -> None:
    with pytest.raises(ClientValidationError):
        RegisterClient(InMemoryClientRepository()).execute(
            user_id="user-1", name=name, email="alice@example.com"
        )


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b"])
def test_rejects_invalid_email(email: str) -> None:
    with pytest.raises(ClientValidationError):
        RegisterClient(InMemoryClientRepository()).execute(
            user_id="user-1", name="Alice", email=email
        )


def test_rejects_invalid_phone() -> None:
    with pytest.raises(ClientValidationError):
        RegisterClient(InMemoryClientRepository()).execute(
            user_id="user-1", name="Alice", email="alice@example.com", phone="abc"
        )
