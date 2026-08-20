"""Lightweight aiohttp frontend for the PDC product-generator network."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aiohttp import ClientError
from aiohttp import ClientSession
from aiohttp import ClientTimeout
from aiohttp import web


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

NEURO_SAN_API_URL = os.getenv(
    "NEURO_SAN_API_URL",
    "http://localhost:8080",
).rstrip("/")

AGENT_NETWORK = os.getenv(
    "PDC_AGENT_NETWORK",
    "pdc_product_generator",
)


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "network": AGENT_NETWORK,
            "neuro_san_api_url": NEURO_SAN_API_URL,
        }
    )


async def generate(request: web.Request) -> web.Response:
    try:
        incoming: dict[str, Any] = await request.json()
    except (ValueError, TypeError):
        return web.json_response(
            {"error": "Request body must be valid JSON."},
            status=400,
        )

    message = incoming.get("message")

    if not isinstance(message, str) or not message.strip():
        return web.json_response(
            {"error": "A natural-language product requirement is required."},
            status=400,
        )

    payload: dict[str, Any] = {
        "user_message": {
            "text": message.strip(),
        }
    }

    chat_context = incoming.get("chat_context")
    if isinstance(chat_context, dict) and chat_context:
        payload["chat_context"] = chat_context

    endpoint = (
        f"{NEURO_SAN_API_URL}/api/v1/"
        f"{AGENT_NETWORK}/streaming_chat"
    )

    try:
        async with request.app["http_session"].post(
            endpoint,
            json=payload,
        ) as response:
            response_text = await response.text()

            if response.status >= 400:
                return web.json_response(
                    {
                        "error": "Neuro SAN rejected the request.",
                        "details": response_text,
                        "status_code": response.status,
                    },
                    status=502,
                )

            try:
                result = await response.json(content_type=None)
            except ValueError:
                return web.json_response(
                    {
                        "error": "Neuro SAN returned a non-JSON response.",
                        "details": response_text,
                    },
                    status=502,
                )

    except (ClientError, TimeoutError) as error:
        return web.json_response(
            {
                "error": "Unable to reach the Neuro SAN API.",
                "details": str(error),
                "target": endpoint,
            },
            status=502,
        )

    return web.json_response(result)


async def create_http_session(app: web.Application) -> None:
    app["http_session"] = ClientSession(
        timeout=ClientTimeout(total=300)
    )


async def close_http_session(app: web.Application) -> None:
    await app["http_session"].close()


def create_app() -> web.Application:
    app = web.Application(client_max_size=2 * 1024 * 1024)

    app.on_startup.append(create_http_session)
    app.on_cleanup.append(close_http_session)

    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/generate", generate)
    app.router.add_static("/static", STATIC_DIR)

    return app


def main() -> None:
    host = os.getenv("PDC_UI_HOST", "127.0.0.1")
    port = int(os.getenv("PDC_UI_PORT", "5002"))

    web.run_app(
        create_app(),
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()