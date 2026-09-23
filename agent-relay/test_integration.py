"""End-to-end test against a running Agent Relay (real HTTP API and database).

Unlike ``test_agent_relay.py`` this does not use an in-process TestClient and
never resets the database. Point it at a live server:

    RELAY_BASE_URL=http://127.0.0.1:8000 uv run pytest -q test_integration.py

It is skipped when ``RELAY_BASE_URL`` is not set.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from worker import run_worker

BASE_URL = os.environ.get("RELAY_BASE_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE_URL, reason="RELAY_BASE_URL is not set")


def register(client: httpx.Client, name: str) -> tuple[dict, dict[str, str]]:
    response = client.post("/api/v1/agents", json={"name": name})
    assert response.status_code == 201, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


def test_two_agents_exchange_task_and_result():
    """SPEC acceptance scenario 1: send, claim, complete, sender reads result."""
    suffix = uuid.uuid4().hex[:8]
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        assert client.get("/ready").status_code == 200

        sender, sender_headers = register(client, f"sender-{suffix}")
        recipient, _ = register(client, f"uppercase-{suffix}")

        sent = client.post(
            "/api/v1/tasks",
            headers=sender_headers,
            json={"to": recipient["agent_id"], "input": "hello relay"},
        )
        assert sent.status_code == 201, sent.text
        task_id = sent.json()["task_id"]
        assert sent.json()["status"] == "queued"

        # The recipient's real worker claims the task over HTTP and completes it.
        asyncio.run(
            asyncio.wait_for(
                run_worker(
                    BASE_URL,
                    recipient["agent_id"],
                    recipient["token"],
                    f"it-worker-{suffix}",
                    wait_seconds=1,
                    stop_after=1,
                ),
                timeout=30,
            )
        )

        task = client.get(f"/api/v1/tasks/{task_id}", headers=sender_headers)
        assert task.status_code == 200, task.text
        body = task.json()
        assert body["status"] == "completed"
        assert body["output"] == "HELLO RELAY"
        assert body["from"] == sender["agent_id"]
        assert body["to"] == recipient["agent_id"]
        assert body["finished_at"] is not None

        attempts = client.get(f"/api/v1/tasks/{task_id}/attempts", headers=sender_headers)
        assert attempts.status_code == 200, attempts.text
        items = attempts.json()["items"]
        assert len(items) == 1
        assert items[0]["attempt"] == 1
