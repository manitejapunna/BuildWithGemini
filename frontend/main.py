"""FastAPI proxy for the Voyage Concierge Agent.

Supports:
1. Local Agent Mode (Direct execution via Runner/App with session persistence).
2. Remote Deployed Agent Mode (A2A over Agent Engine / Agent Runtime).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in browser).
"""

import os
import uuid
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment configuration from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Ensure Vertex AI configuration is strictly active for the GenAI client
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = "qwiklabs-gcp-04-d718c29e3c1e"
if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Optional cloud auth imports if connecting to remote deployed agent
try:
    import google.auth
    import google.auth.transport.requests
    import httpx
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import (
        AgentCard,
        FilePart,
        Message,
        Part,
        Role,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )
    HAVE_A2A = True
except Exception:
    HAVE_A2A = False

# Local ADK runner imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from app.agent import app as adk_app, root_agent

app = FastAPI(title="Voyage Concierge Frontend")

# Local ADK Runner setup with in-memory persistence across turns
session_service = InMemorySessionService()
artifact_service = InMemoryArtifactService()
local_runner = Runner(
    app=adk_app,
    session_service=session_service,
    artifact_service=artifact_service,
    auto_create_session=True,
)

# User session tracking: maps user_id -> adk session_id
_user_sessions: dict[str, str] = {}
# A2A contexts for remote agent mode
_a2a_contexts: dict[str, str] = {}
_remote_card: Any = None

# Remote deployment configuration (if AGENT_ENGINE_RESOURCE_NAME is provided)
RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")


def _get_auth_headers() -> dict[str, str]:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }


async def _chat_remote(message: str, user_id: str) -> list[dict[str, Any]]:
    global _remote_card
    location = RESOURCE.split("/locations/")[1].split("/")[0]
    a2a_base = f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1/{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
    card_url = f"{a2a_base}/.well-known/agent-card.json"

    parts: list[dict[str, Any]] = []
    async with httpx.AsyncClient(headers=_get_auth_headers(), timeout=120) as client:
        if _remote_card is None:
            resp = await client.get(card_url)
            resp.raise_for_status()
            card = AgentCard(**resp.json())
            card.url = a2a_base
            _remote_card = card

        factory = ClientFactory(
            ClientConfig(
                supported_transports=[TransportProtocol.jsonrpc, TransportProtocol.http_json],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(_remote_card)
        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            context_id=_a2a_contexts.get(user_id),
        )

        last_task = None
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _a2a_contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                for p in update.artifact.parts:
                    root = getattr(p, "root", p)
                    if isinstance(root, TextPart) and getattr(root, "text", None):
                        parts.append({"kind": "text", "text": root.text})

        if not parts and last_task is not None:
            for art in getattr(last_task, "artifacts", None) or []:
                for p in art.parts:
                    root = getattr(p, "root", p)
                    if isinstance(root, TextPart) and getattr(root, "text", None):
                        parts.append({"kind": "text", "text": root.text})

    return parts


async def _chat_local(message: str, user_id: str) -> list[dict[str, Any]]:
    session_id = _user_sessions.get(user_id)
    if not session_id:
        session = await session_service.create_session(
            app_name=adk_app.name,
            user_id=user_id,
        )
        session_id = session.id
        _user_sessions[user_id] = session_id

    from google.genai import types

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    )

    response_text = ""
    async for event in local_runner.run_async(
        session_id=session_id,
        user_id=user_id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    response_text += part.text

    if not response_text.strip():
        response_text = "(The agent completed tool execution and state updates.)"

    return [{"kind": "text", "text": response_text}]


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-traveler"

    try:
        if RESOURCE and HAVE_A2A:
            parts = await _chat_remote(message, user_id)
        else:
            parts = await _chat_local(message, user_id)

        if not parts:
            parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
        return JSONResponse({"parts": parts})
    except Exception as exc:
        return JSONResponse(
            status_code=200,
            content={
                "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
            },
        )


@app.get("/api/state")
async def get_state(user_id: str = "web-traveler"):
    session_id = _user_sessions.get(user_id)
    if not session_id:
        return JSONResponse({"profile": None, "checklist": []})
    session = await session_service.get_session(
        app_name=adk_app.name,
        user_id=user_id,
        session_id=session_id,
    )
    if not session:
        return JSONResponse({"profile": None, "checklist": []})

    state = session.state or {}
    return JSONResponse({
        "profile": state.get("traveler_profile"),
        "checklist": state.get("trip_checklist", []),
    })


@app.post("/api/reset")
async def reset_session(req: Request):
    """Creates a brand new clean session for the user."""
    body = await req.json() if req.headers.get("content-type") == "application/json" else {}
    user_id = body.get("user_id") or "web-traveler"

    session = await session_service.create_session(
        app_name=adk_app.name,
        user_id=user_id,
    )
    _user_sessions[user_id] = session.id
    if user_id in _a2a_contexts:
        del _a2a_contexts[user_id]

    return JSONResponse({
        "status": "success",
        "message": "Session reset successfully. Starting with fresh state.",
        "session_id": session.id,
    })


# Mount static assets (HTML/CSS/JS)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
