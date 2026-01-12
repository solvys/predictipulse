"""ESPN data adapter for schedules and results.

Lightweight wrapper over public ESPN scoreboards. No auth required.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("predictipulse.espn")


SPORT_PATHS = {
    "nba": ("basketball", "nba"),
    "nfl": ("football", "nfl"),
    "nhl": ("hockey", "nhl"),
    "mlb": ("baseball", "mlb"),
}


def _date_str(day: _dt.date) -> str:
    return day.strftime("%Y%m%d")


class ESPNAdapter:
    """Fetch game results and basic odds from ESPN public endpoints."""

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self._scoreboard_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _build_scoreboard_url(sport: str, day: _dt.date) -> str:
        sport_path = SPORT_PATHS.get(sport.lower())
        if not sport_path:
            raise ValueError(f"Unsupported sport for ESPN: {sport}")
        cat, league = sport_path
        date_str = _date_str(day)
        return f"https://site.web.api.espn.com/apis/v2/sports/{cat}/{league}/scoreboard?dates={date_str}"

    def fetch_scoreboard(self, sport: str, day: _dt.date) -> Dict[str, Any]:
        """Fetch raw scoreboard JSON with a small in-memory cache."""
        cache_key = f"{sport}:{_date_str(day)}"
        if cache_key in self._scoreboard_cache:
            return self._scoreboard_cache[cache_key]

        url = self._build_scoreboard_url(sport, day)
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
            self._scoreboard_cache[cache_key] = payload
            return payload
        except json.JSONDecodeError as exc:  # pragma: no cover - network
            raise ValueError("Failed to parse ESPN response") from exc

    def get_games(self, sport: str, day: _dt.date) -> List[Dict[str, Any]]:
        """Return simplified game records with scores and winner flag."""
        try:
            data = self.fetch_scoreboard(sport, day)
        except Exception as exc:  # pragma: no cover - network
            logger.warning("ESPN fetch failed for %s %s: %s", sport, day, exc)
            return []

        events = data.get("events", []) or []
        games: List[Dict[str, Any]] = []
        for ev in events:
            competitions = ev.get("competitions") or []
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors") or []
            if len(competitors) < 2:
                continue
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            def _team_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
                score = float(entry.get("score") or 0)
                team = (entry.get("team") or {}).get("displayName") or "Unknown"
                record = entry.get("record") or []
                return {
                    "team": team,
                    "score": score,
                    "winner": bool(entry.get("winner")),
                    "record": record[0]["summary"] if record else "",
                }

            odds = (comp.get("odds") or [{}])[0]
            games.append(
                {
                    "id": ev.get("id"),
                    "name": ev.get("name"),
                    "date": ev.get("date"),
                    "home": _team_payload(home),
                    "away": _team_payload(away),
                    "completed": comp.get("status", {}).get("type", {}).get("completed", False),
                    "spread": odds.get("details"),
                    "home_favorite": odds.get("homeTeamOdds", {}).get("favorite"),
                    "spread_points": odds.get("spread"),
                }
            )
        return games

    def get_results_range(self, sport: str, start: _dt.date, end: _dt.date) -> List[Dict[str, Any]]:
        """Fetch games for date range inclusive."""
        days = (end - start).days
        if days < 0:
            raise ValueError("end date must be >= start date")

        results: List[Dict[str, Any]] = []
        for i in range(days + 1):
            day = start + _dt.timedelta(days=i)
            results.extend(self.get_games(sport, day))
        return results

    def get_winner_lookup(
        self,
        sport: str,
        start: _dt.date,
        end: _dt.date,
    ) -> Dict[str, str]:
        """
        Build a lookup of matchup -> winning team name for quick scoring in backtests.

        The matchup key is formatted as "Away at Home" to align with edge detection.
        """
        lookup: Dict[str, str] = {}
        for game in self.get_results_range(sport, start, end):
            home = game.get("home", {}).get("team") or "Home"
            away = game.get("away", {}).get("team") or "Away"
            winner = home if game.get("home", {}).get("winner") else away
            matchup = f"{away} at {home}"
            lookup[matchup] = winner
        return lookup

