"""Backtest simulator using ESPN results."""

from __future__ import annotations

import datetime as _dt
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from espn_adapter import ESPNAdapter


def _parse_date(date_str: str) -> _dt.date:
    return _dt.datetime.strptime(date_str, "%Y-%m-%d").date()


class BacktestEngine:
    """Lightweight backtester that replays games and scores bets."""

    def __init__(self, espn_adapter: Optional[ESPNAdapter] = None) -> None:
        self.espn = espn_adapter or ESPNAdapter()

    def run_backtest(
        self,
        sports: List[str],
        start_date: str,
        end_date: str,
        stake: float = 10.0,
        edge_threshold: float = 0.05,
        starting_balance: float = 1000.0,
    ) -> Dict[str, Any]:
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        trades: List[Dict[str, Any]] = []

        for sport in sports:
            winner_lookup = self.espn.get_winner_lookup(sport, start, end)
            for matchup, winner in winner_lookup.items():
                home_team = matchup.split(" at ")[1]
                away_team = matchup.split(" at ")[0]
                # Simulated model probabilities
                true_prob_home = random.uniform(0.45, 0.65)
                market_prob_home = max(0.35, min(0.65, true_prob_home - random.uniform(0.02, 0.08)))
                edge_home = true_prob_home - market_prob_home

                selected_team = home_team if edge_home >= edge_threshold else away_team
                true_prob = true_prob_home if selected_team == home_team else (1 - true_prob_home)
                market_prob = market_prob_home if selected_team == home_team else (1 - market_prob_home)
                edge = true_prob - market_prob

                if edge < edge_threshold:
                    continue

                win = selected_team == winner
                pnl = stake * (1 / market_prob - 1) if win else -stake
                trades.append(
                    {
                        "id": f"bt-{sport}-{int(time.time()*1000)}-{len(trades)}",
                        "sport": sport,
                        "matchup": matchup,
                        "team": selected_team,
                        "timestamp": time.time(),
                        "stake": round(stake, 2),
                        "true_prob": round(true_prob, 3),
                        "market_prob": round(market_prob, 3),
                        "edge": round(edge * 100, 2),
                        "result": "WIN" if win else "LOSS",
                        "pnl": round(pnl, 2),
                    }
                )

        summary = self._summarize(trades, starting_balance)
        return {"summary": summary, "trades": trades}

    def _summarize(self, trades: List[Dict[str, Any]], starting_balance: float = 1000.0) -> Dict[str, Any]:
        pnl_total = sum(t["pnl"] for t in trades)
        wins = len([t for t in trades if t["pnl"] > 0])
        losses = len([t for t in trades if t["pnl"] < 0])
        stakes = sum(t["stake"] for t in trades)
        # ROI based on starting balance
        roi = (pnl_total / starting_balance * 100) if starting_balance > 0 else 0.0
        returns = [t["pnl"] / t["stake"] for t in trades if t["stake"]]
        sharpe = (sum(returns) / len(returns)) / (self._stddev(returns) or 1) if returns else 0.0
        max_drawdown = self._max_drawdown([t["pnl"] for t in trades], starting_balance)
        ending_balance = starting_balance + pnl_total

        return {
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / len(trades) * 100) if trades else 0.0, 2),
            "pnl": round(pnl_total, 2),
            "roi": round(roi, 2),
            "sharpe": round(sharpe, 3),
            "max_drawdown": round(max_drawdown, 2),
            "ending_balance": round(ending_balance, 2),
        }

    @staticmethod
    def _stddev(values: List[float]) -> float:
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return math.sqrt(variance)

    @staticmethod
    def _max_drawdown(pnls: List[float], starting_balance: float = 1000.0) -> float:
        balance = starting_balance
        peak = starting_balance
        max_dd = 0.0
        for pnl in pnls:
            balance += pnl
            peak = max(peak, balance)
            max_dd = min(max_dd, balance - peak)
        return max_dd
