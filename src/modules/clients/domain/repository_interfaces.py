"""ChronoLog clients repository port (pure domain, stdlib + domain only)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.value_objects import ClientId


class IClientRepository(ABC):
    """Persistence port for the Client aggregate root.

    Every read is scoped by ``user_id`` so a professional can only
    access their own clients (IDOR prevention). ``save`` carries the
    owner inside ``client.user_id``.
    """

    @abstractmethod
    def save(self, client: Client) -> None:
        """Persist a new or updated client."""
        raise NotImplementedError

    @abstractmethod
    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        """Return the client owned by ``user_id``, or ``None``."""
        raise NotImplementedError

    @abstractmethod
    def list_by_user_id(self, user_id: str) -> list[Client]:
        """List all clients owned by ``user_id``."""
        raise NotImplementedError
