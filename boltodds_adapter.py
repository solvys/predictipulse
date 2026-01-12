"""
BoltOdds WebSocket adapter.

Docs: https://boltodds.com/docs
Connection: wss://spro.agency/api?key=YOUR_TOKEN
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

import requests

WS_URL = "wss://spro.agency/api"
INFO_URL = "https://spro.agency/api/get_info"
GAMES_URL = "https://spro.agency/api/get_games"
MARKETS_URL = "https://spro.agency/api/get_markets"

logger = logging.getLogger("predictipulse.boltodds")


def american_to_prob(odds: float) -> float:
    """Convert American odds to implied probability (0-1)."""
    try:
        odds = float(odds)
    except (TypeError, ValueError):
        return 0.0
    if odds == 0:
        return 0.0
    if odds > 0:
        return 100 / (odds + 100)
    return -odds / (-odds + 100)


class BoltOddsClient:
    def __init__(
        self,
        api_key: str,
        sports: Optional[List[str]] = None,
        sportsbooks: Optional[List[str]] = None,
        markets: Optional[List[str]] = None,
        games: Optional[List[str]] = None,
        reconnect_seconds: int = 5,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.api_key = api_key
        self.sports = sports or ["NBA", "NFL", "MLB", "NHL"]
        self.sportsbooks = sportsbooks or []
        self.markets = markets or []
        self.games = games or []
        self.reconnect_seconds = reconnect_seconds
        self.on_message = on_message
        self._running = False

    def fetch_info(self) -> Dict[str, Any]:
        resp = requests.get(INFO_URL, params={"key": self.api_key}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_games(self) -> Dict[str, Any]:
        resp = requests.get(GAMES_URL, params={"key": self.api_key}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def fetch_markets(self) -> Dict[str, Any]:
        params = {"key": self.api_key}
        if self.sports:
            params["sports"] = ",".join(self.sports)
        if self.sportsbooks:
            params["sportsbooks"] = ",".join(self.sportsbooks)
        resp = requests.get(MARKETS_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    async def _subscribe(self, websocket) -> None:
        subscribe_message = {
          "action": "subscribe",
          "filters": {}
        }
        if self.sports:
            subscribe_message["filters"]["sports"] = self.sports
        if self.sportsbooks:
            subscribe_message["filters"]["sportsbooks"] = self.sportsbooks
        if self.markets:
            subscribe_message["filters"]["markets"] = self.markets
        if self.games:
            subscribe_message["filters"]["games"] = self.games
        await websocket.send(json.dumps(subscribe_message))

    async def _handle_stream(self, websocket) -> None:
        async for raw_msg in websocket:
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                continue
            if self.on_message:
                self.on_message(msg)

    async def connect(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError as exc:
            raise RuntimeError("websockets package not installed") from exc

        self._running = True
        uri = f"{WS_URL}?key={self.api_key}"
        while self._running:
            try:
                async with websockets.connect(uri, ping_interval=20) as websocket:
                    ack_message = await websocket.recv()
                    logger.info("BoltOdds connected: %s", ack_message)
                    await self._subscribe(websocket)
                    await self._handle_stream(websocket)
            except Exception as exc:  # pragma: no cover - network/runtime errors
                logger.warning("BoltOdds disconnected: %s", exc)
                await asyncio.sleep(self.reconnect_seconds)

    def stop(self) -> None:
        self._running = False
