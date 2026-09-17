"""ChronoLog web entrypoint (composition -> Gradio server).

Only ``src/main.py`` (with ``src/composition.py``) may build concrete
adapters. Run locally via ``python -m src.main`` or in Docker (CMD).
"""

from __future__ import annotations

import os

from src.composition import build_context, ensure_schema
from src.presentation.app import UIDeps, build_demo


def build_deps() -> UIDeps:
    """Wire Postgres adapters + use-cases + session middleware deps."""
    ctx = build_context()
    return UIDeps(
        register_user=ctx.register_user,
        authenticate_user=ctx.authenticate_user,
        register_client=ctx.register_client,
        schedule_appointment=ctx.schedule_appointment,
        complete_appointment=ctx.complete_appointment,
        get_history=ctx.get_history,
        sessions=ctx.sessions,
        clients_repo=ctx.clients,
        appointments_repo=ctx.appointments,
        limiter=ctx.limiter,
    )


def main() -> None:
    """Ensure schema, then serve Gradio on 0.0.0.0:7860."""
    ensure_schema()
    demo = build_demo(build_deps())
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_PORT", "7860")),
        show_error=True,
    )


if __name__ == "__main__":
    main()
