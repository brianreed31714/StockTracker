"""Regression contract for the read-only StockTracker GitHub host heartbeat.

The GitHub status branch is a remote observation, not loaded-code attestation.
No Windows service restart or trading operation is involved in this test.
"""
from infrastructure.windows_activation_attestation import REMOTE_HEARTBEAT_SECONDS


def test_host_status_refreshes_at_least_hourly_when_unchanged():
    assert REMOTE_HEARTBEAT_SECONDS == 60 * 60
