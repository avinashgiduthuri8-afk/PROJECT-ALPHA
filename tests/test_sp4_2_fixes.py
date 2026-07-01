"""
SP4.2 regression tests.

BUG-49: VGX scanner_bridge had no signal staleness check.
Fixed:
  - VGX_MAX_SIGNAL_AGE_SECONDS added to config.py (default 300s).
  - signal_age_seconds() utility added to scanner_bridge.py.
  - process_scanner_signal() rejects signals older than the threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# signal_age_seconds() unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalAgeSeconds:

    def _age(self, signal: dict):
        from bots.volatile_gridX.scanner_bridge import signal_age_seconds
        return signal_age_seconds(signal)

    def _iso(self, delta_seconds: float) -> str:
        """Return an ISO timestamp that is `delta_seconds` in the past."""
        ts = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
        return ts.isoformat()

    def test_returns_approximate_age_for_recent_signal(self):
        """A signal timestamped 10 s ago should return age ≈ 10 s."""
        signal = {"coin": "BTC", "timestamp": self._iso(10)}
        age = self._age(signal)
        assert age is not None
        assert 9 <= age <= 15, f"Expected age ~10s, got {age}"

    def test_returns_none_when_no_timestamp_key(self):
        """Signal with no 'timestamp' key must return None."""
        assert self._age({"coin": "BTC", "score": 80}) is None

    def test_returns_none_when_timestamp_is_empty_string(self):
        """Signal with empty 'timestamp' value must return None."""
        assert self._age({"coin": "BTC", "timestamp": ""}) is None

    def test_returns_none_for_malformed_timestamp(self):
        """Malformed timestamp must return None without raising."""
        assert self._age({"coin": "BTC", "timestamp": "not-a-date"}) is None

    def test_handles_naive_timestamp(self):
        """Naive ISO timestamp (no timezone) is treated as UTC."""
        naive_ts = (datetime.utcnow() - timedelta(seconds=20)).isoformat()
        signal = {"coin": "ETH", "timestamp": naive_ts}
        age = self._age(signal)
        assert age is not None
        assert 19 <= age <= 25, f"Expected age ~20s, got {age}"


# ─────────────────────────────────────────────────────────────────────────────
# process_scanner_signal() staleness gate
# ─────────────────────────────────────────────────────────────────────────────

class TestBug49StalenessGate:

    def _iso(self, delta_seconds: float) -> str:
        ts = datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
        return ts.isoformat()

    def _bridge_signal(self, age_offset: float | None = None) -> dict:
        """Build a minimal scanner signal; omit timestamp if age_offset is None."""
        sig = {"coin": "BTC", "score": 85.0}
        if age_offset is not None:
            sig["timestamp"] = self._iso(age_offset)
        return sig

    def _max_age(self) -> int:
        from bots.volatile_gridX.config import VGX_MAX_SIGNAL_AGE_SECONDS
        return VGX_MAX_SIGNAL_AGE_SECONDS

    def test_rejects_signal_older_than_threshold(self):
        """Signal timestamped max_age + 1 s ago must be REJECTED."""
        from bots.volatile_gridX import scanner_bridge

        stale_signal = self._bridge_signal(self._max_age() + 1)

        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            result = scanner_bridge.process_scanner_signal(stale_signal)

        assert result["result"] == "REJECTED", (
            f"Expected REJECTED for stale signal, got: {result}"
        )
        assert "old" in result["reason"].lower() or "age" in result["reason"].lower(), (
            f"Rejection reason should mention staleness: {result['reason']}"
        )
        fake_validate.assert_not_called()
        fake_execute.assert_not_called()

    def test_accepts_signal_younger_than_threshold(self):
        """Signal timestamped max_age - 1 s ago must pass the staleness gate."""
        from bots.volatile_gridX import scanner_bridge

        fresh_signal = self._bridge_signal(self._max_age() - 1)

        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Paper trade executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            result = scanner_bridge.process_scanner_signal(fresh_signal)

        fake_validate.assert_called_once()

    def test_accepts_signal_with_no_timestamp(self):
        """Signal with no 'timestamp' key must not be rejected for staleness (age=None)."""
        from bots.volatile_gridX import scanner_bridge

        signal_no_ts = self._bridge_signal(None)

        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            result = scanner_bridge.process_scanner_signal(signal_no_ts)

        assert result.get("reason") != "Signal too old", (
            "Signal with no timestamp should not be rejected for staleness"
        )
        fake_validate.assert_called_once()

    def test_staleness_rejection_logged_in_scanner_rejections(self):
        """A staleness rejection must appear in scanner_rejections list."""
        from bots.volatile_gridX import scanner_bridge

        stale_signal = self._bridge_signal(self._max_age() + 60)

        original_rejections = scanner_bridge.scanner_rejections[:]
        fake_validate = MagicMock(return_value=(True, "OK", {}))
        fake_execute  = MagicMock(return_value=(True, "Executed"))

        with patch.object(scanner_bridge, "validate_signal",  fake_validate), \
             patch.object(scanner_bridge, "paper_execute_signal", fake_execute):
            scanner_bridge.process_scanner_signal(stale_signal)

        new_rejections = scanner_bridge.scanner_rejections[len(original_rejections):]
        assert any("BTC" == r.get("coin") for r in new_rejections), (
            "Staleness rejection not added to scanner_rejections"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Config constant
# ─────────────────────────────────────────────────────────────────────────────

class TestVgxMaxSignalAgeConfig:

    def test_constant_exists_and_is_int(self):
        """VGX_MAX_SIGNAL_AGE_SECONDS must exist in config and be an int."""
        from bots.volatile_gridX.config import VGX_MAX_SIGNAL_AGE_SECONDS
        assert isinstance(VGX_MAX_SIGNAL_AGE_SECONDS, int)

    def test_default_is_300(self):
        """Default value must be 300 when env var is unset."""
        import os
        from bots.volatile_gridX import config
        original = os.environ.pop("VGX_MAX_SIGNAL_AGE_SECONDS", None)
        try:
            assert config.VGX_MAX_SIGNAL_AGE_SECONDS == 300
        finally:
            if original is not None:
                os.environ["VGX_MAX_SIGNAL_AGE_SECONDS"] = original
