"""ChronoLog server-side AuthN/AuthZ helpers (stdlib + auth domain only).

No web-framework imports here — the Gradio presentation layer calls these
functions with the raw token string. Keeps the middleware testable without
a running server (TSK-015 scope honesty: no routes invented, only the
contract + its unit tests).
"""
