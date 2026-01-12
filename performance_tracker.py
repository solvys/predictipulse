"""Performance tracking and backtest run storage."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Tuple

Source = Literal["paper", "actual"]


class PerformanceTracker:
    """Lightweight SQLite-backed tracker for rolling performance."""

    def __init__(self, db_path: str = "performance.db") -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    # ------------------------------------------------------------------ #
    # Setup
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    ts REAL NOT NULL,
                    pnl REAL NOT NULL,
                    stake REAL NOT NULL,
                    edge REAL DEFAULT 0,
                    result TEXT,
                    matchup TEXT,
                    team TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_trades_ts_source ON trades(ts, source);

                CREATE TABLE IF NOT EXISTS backtests (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    sports TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    summary TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_backtests_created ON backtests(created_at);
                """
            )

    # ------------------------------------------------------------------ #
    # Trade logging
    # ------------------------------------------------------------------ #
    def log_trade(self, trade: Dict[str, Any], source: Source) -> None:
        """Insert or update a trade record."""
        if not trade.get("id"):
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades (
                    id, source, ts, pnl, stake, edge, result, matchup, team
                )
                VALUES (:id, :source, :ts, :pnl, :stake, :edge, :result, :matchup, :team)
                """,
                {
                    "id": str(trade["id"]),
                    "source": source,
                    "ts": float(trade.get("timestamp") or time.time()),
                    "pnl": float(trade.get("pnl") or 0.0),
                    "stake": float(trade.get("stake") or 0.0),
                    "edge": float(trade.get("edge") or 0.0),
                    "result": trade.get("result"),
                    "matchup": trade.get("matchup"),
                    "team": trade.get("team"),
                },
            )

    def bulk_log(self, trades: Iterable[Dict[str, Any]], source: Source) -> None:
        for trade in trades:
            self.log_trade(trade, source)

    # ------------------------------------------------------------------ #
    # Metrics
    # ------------------------------------------------------------------ #
    def _fetch_trades_since(self, days: int, source: Source) -> List[sqlite3.Row]:
        cutoff = time.time() - days * 86400
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE source=? AND ts>=? ORDER BY ts DESC",
                (source, cutoff),
            ).fetchall()
        return rows

    def get_rolling_metrics(self, days: int = 7, source: Source = "paper") -> Dict[str, Any]:
        rows = self._fetch_trades_since(days, source)
        pnl_total = sum(r["pnl"] for r in rows)
        stakes = [r["stake"] for r in rows if r["stake"]]
        trades = len(rows)
        wins = len([r for r in rows if r["pnl"] > 0])
        losses = len([r for r in rows if r["pnl"] < 0])
        win_rate = (wins / trades * 100) if trades else 0.0
        roi = (pnl_total / sum(stakes)) * 100 if stakes else 0.0
        avg_edge = sum(r["edge"] for r in rows) / trades if trades else 0.0

        daily = self._daily_breakdown(rows, days)

        return {
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "pnl": round(pnl_total, 2),
            "win_rate": round(win_rate, 2),
            "roi": round(roi, 2),
            "avg_edge": round(avg_edge, 3),
            "daily": daily,
        }

    def _daily_breakdown(self, rows: List[sqlite3.Row], days: int) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        now = time.time()
        for i in range(days - 1, -1, -1):
            day_start = now - i * 86400
            key = time.strftime("%Y-%m-%d", time.localtime(day_start))
            buckets[key] = {"date": key, "pnl": 0.0, "trades": 0}

        for r in rows:
            key = time.strftime("%Y-%m-%d", time.localtime(r["ts"]))
            if key in buckets:
                buckets[key]["pnl"] += r["pnl"]
                buckets[key]["trades"] += 1

        return list(buckets.values())

    def get_history(self, limit: int = 50, source: Source = "paper") -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE source=? ORDER BY ts DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Backtest run storage
    # ------------------------------------------------------------------ #
    def store_backtest(
        self,
        backtest_id: str,
        sports: List[str],
        start_date: str,
        end_date: str,
        summary: Dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backtests (
                    id, created_at, sports, start_date, end_date, summary
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    backtest_id,
                    time.time(),
                    ",".join(sports),
                    start_date,
                    end_date,
                    json.dumps(summary),
                ),
            )

    def list_backtests(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM backtests ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results: List[Dict[str, Any]] = []
        for r in rows:
            payload = dict(r)
            try:
                payload["summary"] = json.loads(payload.get("summary") or "{}")
            except json.JSONDecodeError:
                payload["summary"] = {}
            results.append(payload)
        return results
