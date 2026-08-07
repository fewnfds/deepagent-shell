from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import httpx
import hashlib
import re
from fastapi.testclient import TestClient

from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.database import SQLiteDatabase


MANAGEMENT_TOKEN = "test-management-token"
API_KEY = "test-api-key"


def configure_scope_tokens(monkeypatch, root: Path) -> None:
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", MANAGEMENT_TOKEN)
    database = SQLiteDatabase(
        root / "data" / "state" / "agent-shell.sqlite3"
    )
    store = ApiServerStore(database)
    if store.api_key() is None:
        store.update_settings(
            api_key_operation="replace",
            api_key=API_KEY,
        )


class ScopedAuthTestClient(TestClient):
    """Attach the matching test Bearer token unless a test supplies its own."""

    def request(self, method, url, **kwargs):
        headers = httpx.Headers(kwargs.get("headers"))
        path = urlsplit(str(url)).path
        # Current Main Agent contract requires a stable agent-* public id. Most
        # older fixtures are intentionally focused on capability behavior; keep
        # that fixture noise local to tests instead of weakening the backend.
        body = kwargs.get("json")
        if (
            isinstance(body, dict)
            and (
                path == "/api/main-agents"
                or (method.upper() == "PUT" and re.fullmatch(r"/api/main-agents/[^/]+", path))
            )
            and "public_id" not in body
            and isinstance(body.get("name"), str)
        ):
            slug = re.sub(r"[^a-z]+", "-", body["name"].lower()).strip("-")
            digest = hashlib.sha256(body["name"].encode("utf-8")).digest()[:6]
            suffix = "".join(chr(ord("a") + value % 26) for value in digest)
            body = {**body, "public_id": f"agent-{slug or 'test'}-{suffix}"}
            kwargs["json"] = body
        if "authorization" not in headers:
            if path == "/api" or path.startswith("/api/"):
                headers["Authorization"] = f"Bearer {MANAGEMENT_TOKEN}"
            elif path == "/v1" or path.startswith("/v1/"):
                headers["Authorization"] = f"Bearer {API_KEY}"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)
