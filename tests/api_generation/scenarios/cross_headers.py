"""Call the response headers server through its client: header text that is not ASCII, as the server writes it.

Starlette writes a header value in Latin-1 and HTTPX2 reads it back, so the client decodes the text the service
gave, for a single value and for each item of an array. The calls run over an ASGI transport and a socket only:
Starlette's test client reads response headers as UTF-8, which is not what a server sends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from tests.api_generation.support.cross_targets import service

if TYPE_CHECKING:
    from types import ModuleType

    from tests.api_generation.support.cross_targets import Calls, Kit, Recorder

DOCUMENT = "cross/response-headers.yaml"
SOCKET = True


def services(server: ModuleType, models: ModuleType, record: Recorder) -> dict[str, object]:
    """Return a service that answers with header text beyond ASCII."""
    del models
    headers = {"X-Name": "café", "X-Tags": "café,b"}
    return {
        "default": service(
            server.services.DefaultService, record, get_text=lambda: server.HTTPResult(204, None, headers=headers)
        )
    }


def calls(kit: Kit) -> Calls:
    """Return a call that decodes each declared header and reads the received ones."""
    if isinstance(kit.http, TestClient):
        return []
    header = kit.module("types.default").decode_get_text_header
    return [
        (
            "get_text",
            lambda: kit.then(
                kit.api.default.with_response.get_text(),
                lambda result: (
                    header(result.info, name="X-Name"),
                    header(result.info, name="X-Tags"),
                    result.info.headers.get_all("x-name"),
                    result.info.headers.get_all("x-tags"),
                ),
            ),
        )
    ]
