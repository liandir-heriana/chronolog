"""TSK-007 RED: IClientRepository port (domain, pure DIP).

Written BEFORE production code. Must FAIL on collection until
`src/modules/clients/domain/repository_interfaces.py` exists.
"""

import inspect
from abc import ABC

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId, Email


def _make_client(user_id: str, name: str = "Ada Lovelace") -> Client:
    return Client(
        id=ClientId.generate(),
        user_id=user_id,
        name=name,
        email=Email("ada@example.com"),
    )


class TestIClientRepositoryContract:
    def test_is_abstract_base_class(self) -> None:
        assert issubclass(IClientRepository, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        try:
            IClientRepository()  # type: ignore[abstract]
        except TypeError:
            return
        raise AssertionError("IClientRepository must not be directly instantiable")

    def test_declares_required_abstract_methods(self) -> None:
        assert set(IClientRepository.__abstractmethods__) == {
            "save",
            "find_by_id_and_user_id",
            "list_by_user_id",
        }

    def test_every_read_method_requires_user_id(self) -> None:
        for method_name in ("find_by_id_and_user_id", "list_by_user_id"):
            params = inspect.signature(getattr(IClientRepository, method_name)).parameters
            assert "user_id" in params, f"{method_name} must require user_id"


class InMemoryClientRepository(IClientRepository):
    """Minimal fake used to prove the port is implementable and isolates users."""

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


class TestIClientRepositoryIsolation:
    def test_round_trip_and_user_id_isolation(self) -> None:
        repo: IClientRepository = InMemoryClientRepository()
        mine = _make_client("user-1")
        other = _make_client("user-2")
        repo.save(mine)
        repo.save(other)

        assert repo.find_by_id_and_user_id(mine.id, "user-1") == mine
        # Other user's data must be invisible, even with a valid id.
        assert repo.find_by_id_and_user_id(mine.id, "user-2") is None
        assert repo.find_by_id_and_user_id(other.id, "user-1") is None

        mine_only = repo.list_by_user_id("user-1")
        assert mine_only == [mine]
        assert all(c.user_id == "user-1" for c in mine_only)
