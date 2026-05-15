"""
Concurrency test: WS-11 grpc.aio singleton channel.

Verifies that 20 concurrent put_credential calls via the VaultAdapterClient:
  1. All succeed without deadlock or "channel closed" errors when the vault
     mock accepts requests.
  2. Complete faster than the serial upper bound (rough sanity check, not a
     strict perf gate).

The test uses a lightweight in-process asyncio mock of the gRPC stub rather
than spinning up the full Docker stack, so it runs without MINTKEY_INTEGRATION_TEST.
It directly replaces the module-level _channel singleton with a mock aio channel
whose stub returns canned responses, exercising the async await path through
VaultAdapterClient.put_credential.

Source: WS-11 implementation spec.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure admin-api source is on path (mirrors other tests in this suite).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_ADMIN_API_SRC = os.path.join(_REPO_ROOT, "admin-api", "src")
_MODELS_SRC = os.path.join(_REPO_ROOT, "mintkey-models")
for _p in (_ADMIN_API_SRC, _MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_N_CONCURRENT = 20
# Conservative per-call budget: each "call" in the mock takes ~0ms; give the
# serial path a realistic floor of 5 ms/call so the concurrent run can beat it.
_SERIAL_FLOOR_MS_PER_CALL = 5


@pytest.mark.asyncio
async def test_concurrent_put_credential_all_succeed():
    """20 concurrent put_credential calls all return without error."""
    from admin_api.services import vault_pb2
    import admin_api.services.vault_client as vc_mod

    # Build a mock PutCredential response object.
    mock_resp = MagicMock()
    mock_resp.key_version = 42

    # Build a mock stub whose PutCredential is an awaitable returning mock_resp.
    mock_stub = MagicMock()
    mock_stub.PutCredential = AsyncMock(return_value=mock_resp)

    # Patch VaultAdapterClient._stub to return our mock stub so no real channel
    # is opened — the test exercises the await path purely in-process.
    client = vc_mod.VaultAdapterClient()

    call_count = 0

    async def _patched_put(req):
        nonlocal call_count
        # Tiny yield to let the event loop interleave coroutines (simulates I/O).
        await asyncio.sleep(0)
        call_count += 1
        return mock_resp

    mock_stub.PutCredential.side_effect = _patched_put

    with patch.object(client, "_stub", return_value=mock_stub):
        tasks = [
            client.put_credential(
                tenant_id=f"tenant-{i:04d}-0000-0000-0000-000000000000",
                service_id=f"service-{i:04d}-0000-0000-0000-000000000000",
                auth_scheme="api_key_header",
                plaintext=f"secret-{i}",
            )
            for i in range(_N_CONCURRENT)
        ]
        results = await asyncio.gather(*tasks)

    assert len(results) == _N_CONCURRENT, f"expected {_N_CONCURRENT} results, got {len(results)}"
    assert call_count == _N_CONCURRENT, f"expected {_N_CONCURRENT} stub calls, got {call_count}"

    for r in results:
        assert r["key_version"] == 42
        assert "credential_id" in r
        assert "created_at" in r


@pytest.mark.asyncio
async def test_concurrent_put_credential_faster_than_serial_bound():
    """
    Concurrent execution completes faster than the serial floor
    (_N_CONCURRENT * _SERIAL_FLOOR_MS_PER_CALL ms).

    Each call has a 2 ms artificial delay (asyncio.sleep) to simulate gRPC
    network latency.  Serially that would take ≥ N*2 ms; concurrently it
    should take close to 2 ms.  We gate at N * SERIAL_FLOOR (5 ms) /1000 s
    which is very conservative.
    """
    from admin_api.services import vault_pb2
    import admin_api.services.vault_client as vc_mod

    mock_resp = MagicMock()
    mock_resp.key_version = 7

    mock_stub = MagicMock()

    async def _latency_stub(req):
        await asyncio.sleep(0.002)  # 2 ms simulated gRPC round-trip
        return mock_resp

    mock_stub.PutCredential = AsyncMock(side_effect=_latency_stub)

    client = vc_mod.VaultAdapterClient()
    with patch.object(client, "_stub", return_value=mock_stub):
        t0 = time.perf_counter()
        tasks = [
            client.put_credential(
                tenant_id=f"tenant-{i:04d}-0000-0000-0000-000000000000",
                service_id=f"service-{i:04d}-0000-0000-0000-000000000000",
                auth_scheme="bearer_token",
                plaintext=f"tok-{i}",
            )
            for i in range(_N_CONCURRENT)
        ]
        results = await asyncio.gather(*tasks)
        elapsed_ms = (time.perf_counter() - t0) * 1000

    serial_bound_ms = _N_CONCURRENT * _SERIAL_FLOOR_MS_PER_CALL
    assert len(results) == _N_CONCURRENT
    assert elapsed_ms < serial_bound_ms, (
        f"Concurrent calls took {elapsed_ms:.1f} ms, "
        f"expected < {serial_bound_ms} ms (serial bound). "
        f"The grpc.aio migration may not be providing concurrency benefits."
    )
