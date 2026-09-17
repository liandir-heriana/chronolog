"""ChronoLog RegisterClient use case (depends only on IClientRepository port)."""

from __future__ import annotations

from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId, Email, Phone


class RegisterClient:
    """Register a client profile owned by ``user_id``.

    Flow: value objects validate (name/email/phone rules from TSK-005) ->
    ``Client`` binds the owner -> ``save`` and return. Every read downstream
    stays scoped by ``user_id`` (IDOR prevention); this mutation carries the
    owner inside ``client.user_id`` so the adapter upsert stays guarded.
    """

    def __init__(self, clients: IClientRepository) -> None:
        self._clients = clients

    def execute(
        self,
        *,
        user_id: str,
        name: str,
        email: str,
        phone: str | None = None,
    ) -> Client:
        """Create, persist, and return the new client for ``user_id``."""
        address = Email(email)
        number = Phone(phone) if phone is not None and phone.strip() else None
        client = Client(
            id=ClientId.generate(),
            user_id=user_id,
            name=name,
            email=address,
            phone=number,
        )
        self._clients.save(client)
        return client
