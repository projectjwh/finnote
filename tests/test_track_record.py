"""Tests for track record ledger and scorecard computation."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from finnote.agents.base import Conviction, ResearchCall
from finnote.track_record.ledger import TrackRecordLedger
from finnote.track_record.scorecard import compute_scorecard


def _make_call(**kwargs) -> ResearchCall:
    defaults = dict(
        direction="bullish",
        asset_class="equity",
        instrument="SPX",
        entry_level="5200",
        target_level="5600",
        stop_level="4900",
        risk_reward_ratio=1.33,
        time_horizon="3M",
        conviction=Conviction.HIGH,
        thesis="Test thesis",
        falsification_criteria="Test falsification",
    )
    defaults.update(kwargs)
    return ResearchCall(**defaults)


def test_ledger_publish_and_retrieve():
    """Can publish a call and retrieve it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ledger = TrackRecordLedger(db_path)

        call = _make_call()
        call_id = ledger.publish_call(call)

        open_calls = ledger.get_open_calls()
        assert len(open_calls) == 1
        assert open_calls[0]["call_id"] == call_id
        assert open_calls[0]["status"] == "published"
        assert open_calls[0]["instrument"] == "SPX"

        ledger.close()


def test_ledger_close_call():
    """Can close a published call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ledger = TrackRecordLedger(db_path)

        call = _make_call()
        call_id = ledger.publish_call(call)

        ledger.update_call_status(
            call_id, "target_hit",
            close_level="5600",
            pnl_native_units=400.0,
        )

        open_calls = ledger.get_open_calls()
        assert len(open_calls) == 0

        closed_calls = ledger.get_closed_calls()
        assert len(closed_calls) == 1
        assert closed_calls[0]["status"] == "target_hit"
        assert closed_calls[0]["pnl_native_units"] == 400.0

        ledger.close()


def test_scorecard_empty():
    """Scorecard handles empty call list."""
    stats = compute_scorecard([])
    assert stats.total_calls == 0
    assert stats.batting_average == 0.0


def test_scorecard_with_calls():
    """Scorecard computes correct statistics."""
    calls = [
        {"status": "target_hit", "pnl_native_units": 400.0,
         "conviction": "high", "product": "daily",
         "published_date": "2026-01-01T00:00:00",
         "close_date": "2026-02-01T00:00:00"},
        {"status": "target_hit", "pnl_native_units": 200.0,
         "conviction": "medium", "product": "weekly",
         "published_date": "2026-01-15T00:00:00",
         "close_date": "2026-02-15T00:00:00"},
        {"status": "stopped_out", "pnl_native_units": -300.0,
         "conviction": "high", "product": "daily",
         "published_date": "2026-01-10T00:00:00",
         "close_date": "2026-01-20T00:00:00"},
        {"status": "published", "pnl_native_units": None,
         "conviction": "maximum", "product": "monthly"},
    ]
    stats = compute_scorecard(calls)

    assert stats.total_calls == 4
    assert stats.open_calls == 1
    assert stats.closed_calls == 3
    assert stats.target_hit == 2
    assert stats.stopped_out == 1
    assert stats.batting_average == 2 / 3  # 2 wins / 3 decided
    assert stats.avg_gain == 300.0          # (400 + 200) / 2
    assert stats.avg_loss == -300.0
    assert stats.win_loss_ratio == 1.0      # 300 / 300
