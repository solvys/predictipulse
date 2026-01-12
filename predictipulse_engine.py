"""Lightweight Predictipulse engine wrapper for the control panel."""

from __future__ import annotations

import csv
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from queue import SimpleQueue, Empty
from typing import Any, Dict, List, Optional

from kalshi_adapter import KalshiClient
from performance_tracker import PerformanceTracker
from boltodds_adapter import BoltOddsClient, american_to_prob

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


@dataclass
class Trade:
    id: str
    matchup: str
    team: str
    stake: float
    entry_price: float
    true_prob: float
    edge: float
    result: str  # "WIN", "LOSS", "PENDING"
    pnl: float
    timestamp: float


class PredictipulseEngine:
    def __init__(
        self,
        config: Dict[str, Any],
        demo_mode: bool = True,
        performance_tracker: Optional[PerformanceTracker] = None,
    ):
        self.config = dict(config)
        self.demo_mode = demo_mode
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._log_queue: SimpleQueue[str] = SimpleQueue()
        self._opp_queue: SimpleQueue[Dict[str, Any]] = SimpleQueue()
        self._trade_queue: SimpleQueue[Dict[str, Any]] = SimpleQueue()
        self._lock = threading.Lock()
        self.logger = logging.getLogger("predictipulse_engine")
        self.performance_tracker = performance_tracker

        # Stats tracking - default to 0 until we get real data from Kalshi
        self._bankroll = 0.0
        self._initial_bankroll = 0.0
        self._trades: List[Trade] = []
        self._win_count = 0
        self._loss_count = 0
        self._total_pnl = 0.0
        self._live_mode = not demo_mode
        self.kalshi_client: Optional[KalshiClient] = None
        self.boltodds_client: Optional[BoltOddsClient] = None

        if self._live_mode:
            self._init_kalshi_client()
            self._init_boltodds_client()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        self._emit_log("INFO", "PolyPulse engine started.")

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._emit_log("INFO", "PolyPulse engine stopped.")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def update_config(self, new_config: Dict[str, Any]) -> None:
        with self._lock:
            # Don't allow bankroll to be set via config - it comes from Kalshi
            new_config.pop("bankroll", None)
            self.config.update(new_config)
        self._emit_log("INFO", f"Configuration updated: {json.dumps(new_config)}")

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.config)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        if self._live_mode and self.kalshi_client:
            total_trades = len(self._trades)
            win_rate = 0.0
        else:
            total_trades = self._win_count + self._loss_count
            win_rate = (self._win_count / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate average risk to reward ratio
        avg_rr = self._calculate_avg_rr()
        
        return {
            "bankroll": round(self._bankroll, 2),
            "initial_bankroll": self._initial_bankroll,
            "total_pnl": round(self._total_pnl, 2),
            "trades": total_trades,
            "wins": self._win_count,
            "losses": self._loss_count,
            "win_rate": round(win_rate, 1),
            "avg_rr": round(avg_rr, 2),
        }
    
    def _calculate_avg_rr(self) -> float:
        """Calculate average risk to reward ratio from trades."""
        if not self._trades:
            return 0.0
        
        wins = []
        losses = []
        for trade in self._trades:
            pnl = getattr(trade, 'pnl', 0) or 0
            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))
        
        if not wins or not losses:
            return 0.0
        
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        
        if avg_loss == 0:
            return 0.0
        
        return avg_win / avg_loss

    def get_recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [asdict(t) for t in self._trades[-limit:]][::-1]

    # ------------------------------------------------------------------
    # Streaming helpers
    # ------------------------------------------------------------------
    def next_log(self, timeout: float = 1.0) -> Optional[str]:
        try:
            return self._log_queue.get(timeout=timeout)
        except Empty:
            return None

    def next_opportunity(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            return self._opp_queue.get(timeout=timeout)
        except Empty:
            return None

    def next_trade(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            return self._trade_queue.get(timeout=timeout)
        except Empty:
            return None

    # ------------------------------------------------------------------
    # Internal simulation loop (demo mode)
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        if self._live_mode and self.kalshi_client:
            self._emit_log("INFO", "Starting live mode with BoltOdds + Kalshi integration...")
            scan_interval = 30  # seconds between scans
            
            while self._running:
                try:
                    # Refresh account balance
                    self._refresh_kalshi_account()
                    
                    # Fetch data from both sources
                    self._emit_log("INFO", "Scanning for opportunities...")
                    
                    boltodds_games = self._fetch_boltodds_games()
                    boltodds_markets = self._fetch_boltodds_markets()
                    kalshi_markets = self._fetch_kalshi_sports_markets()
                    
                    games_count = len(boltodds_games) if isinstance(boltodds_games, dict) else 0
                    self._emit_log("INFO", f"BoltOdds: {games_count} games | Kalshi: {len(kalshi_markets)} markets")
                    
                    # Parse sharp odds from BoltOdds
                    sharp_games = self._parse_sharp_odds(boltodds_games, boltodds_markets)
                    
                    # Find arbitrage/+EV opportunities
                    opportunities = self._find_opportunities(sharp_games, kalshi_markets)
                    
                    # Emit opportunities to the dashboard
                    for opp in opportunities:
                        self._opp_queue.put(opp)
                        if opp.get("edge", 0) > 0:
                            self._emit_log(
                                "INFO",
                                f"Opportunity: {opp['matchup']} | Edge: {opp['edge']:.2f}% | "
                                f"Stake: ${opp.get('kelly_stake', 0):.2f}"
                            )
                    
                    if not opportunities:
                        self._emit_log("INFO", "No +EV opportunities found this scan.")
                    
                except Exception as exc:
                    self._emit_log("WARNING", f"Scan cycle error: {exc}")
                
                # Wait before next scan
                for _ in range(scan_interval):
                    if not self._running:
                        break
                    time.sleep(1)
            return

        teams = [
            ("Lakers", "Celtics"),
            ("Warriors", "Suns"),
            ("Knicks", "Heat"),
            ("Eagles", "Cowboys"),
            ("Chiefs", "Bills"),
            ("Rangers", "Bruins"),
        ]

        while self._running:
            time.sleep(2)

            home, away = random.choice(teams)
            true_prob = round(random.uniform(0.35, 0.65), 3)
            market_prob = max(0.05, min(0.95, true_prob - random.uniform(0.02, 0.08)))
            edge = (true_prob - market_prob) * 100
            kelly_multiplier = float(self.config.get("kelly_multiplier", 0.5))
            kelly_fraction = max(
                0.0,
                ((true_prob * (1 / market_prob - 1)) - (1 - true_prob))
                / (1 / market_prob - 1),
            )
            stake = self._bankroll * kelly_fraction * kelly_multiplier
            stake = min(stake, float(self.config.get("max_dollar_bet", 50)))
            stake = min(stake, self._bankroll * float(self.config.get("max_percentage_bet", 10)) / 100)

            team = home if random.random() > 0.5 else away

            opp = {
                "matchup": f"{home} vs {away}",
                "team": team,
                "sport": "sim",
                "true_prob": true_prob,
                "market_prob": market_prob,
                "edge": edge,
                "kelly_stake": max(0.0, stake),
                "timestamp": time.time(),
            }
            self._opp_queue.put(opp)
            self._emit_log(
                "INFO",
                f"Opportunity: {opp['matchup']} edge={opp['edge']:.2f}% stake=${opp['kelly_stake']:.2f}",
            )

            # Simulate taking trades on ~40% of opportunities
            if random.random() < 0.4 and stake > 1:
                self._simulate_trade(opp)

    def _simulate_trade(self, opp: Dict[str, Any]) -> None:
        """Simulate a trade with realistic outcome based on true probability."""
        stake = opp["kelly_stake"]
        true_prob = opp["true_prob"]
        market_prob = opp["market_prob"]

        # Simulate outcome - win probability is the true probability
        # (in real trading, you'd wait for game result)
        win = random.random() < true_prob

        if win:
            # Payout is 1/market_prob - 1 (e.g., if market_prob=0.5, payout is 1:1)
            pnl = stake * (1 / market_prob - 1)
            result = "WIN"
            self._win_count += 1
        else:
            pnl = -stake
            result = "LOSS"
            self._loss_count += 1

        self._bankroll += pnl
        self._total_pnl += pnl

        trade = Trade(
            id=f"trade-{int(time.time() * 1000)}",
            matchup=opp["matchup"],
            team=opp["team"],
            stake=round(stake, 2),
            entry_price=opp["market_prob"],
            true_prob=opp["true_prob"],
            edge=opp["edge"],
            result=result,
            pnl=round(pnl, 2),
            timestamp=time.time(),
        )

        self._trades.append(trade)
        self._trade_queue.put(asdict(trade))
        if self.performance_tracker:
            self.performance_tracker.log_trade(asdict(trade), source="paper")

        self._emit_log(
            "INFO" if win else "WARNING",
            f"TRADE {result}: {trade.matchup} ({trade.team}) "
            f"stake=${trade.stake:.2f} → P&L=${trade.pnl:+.2f} "
            f"| Bankroll: ${self._bankroll:.2f}",
        )

    # ------------------------------------------------------------------
    # Kalshi account helpers
    # ------------------------------------------------------------------
    def _load_kalshi_keys(self) -> Optional[Dict[str, str]]:
        """Load Kalshi credentials from kalshi_keys.csv and kalshi_private.pem."""
        base_dir = Path(__file__).parent
        key_path = base_dir / "kalshi_keys.csv"
        # Support both .pem and .txt extensions for the private key
        pem_path = base_dir / "kalshi_private.pem"
        if not pem_path.exists():
            pem_path = base_dir / "kalshi_private_key.txt"
        
        if not key_path.exists():
            return None
        
        # Try to load inline secret from PEM file if it exists
        pem_secret = None
        if pem_path.exists():
            try:
                pem_secret = pem_path.read_text().strip()
            except Exception:
                pass
        
        with key_path.open() as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                api_key = row.get("api_key") or row.get("key")
                api_secret = row.get("api_secret")
                private_key_file = row.get("private_key_file")
                if api_key:
                    # Prefer PEM file content, then csv api_secret, then private_key_file reference
                    return {
                        "api_key": api_key.strip(),
                        "api_secret": pem_secret or (api_secret or "").strip() or None,
                        "private_key_file": (private_key_file or "").strip() or None if not pem_secret else None,
                    }
        return None

    def _init_kalshi_client(self) -> None:
        keys = self._load_kalshi_keys()
        if not keys:
            self._emit_log("WARNING", "Kalshi credentials missing; falling back to demo mode.")
            self.demo_mode = True
            self._live_mode = False
            return
        try:
            # Resolve private key path relative to project directory
            private_key_path = None
            if keys.get("private_key_file"):
                pem_path = Path(__file__).parent / keys["private_key_file"]
                if pem_path.exists():
                    private_key_path = str(pem_path)
                else:
                    self._emit_log("WARNING", f"Private key file not found: {pem_path}")
            
            self.kalshi_client = KalshiClient(
                api_key=keys.get("api_key"),
                api_secret=keys.get("api_secret"),
                api_secret_path=private_key_path,
                demo=False,
            )
            self._refresh_kalshi_account()
            self._emit_log("INFO", "Kalshi client initialized and account synced.")
        except Exception as exc:  # pragma: no cover - network errors
            self._emit_log("WARNING", f"Kalshi init failed, using demo mode: {exc}")
            self.demo_mode = True
            self._live_mode = False

    def _convert_positions_to_trades(self, positions: List[Dict[str, Any]]) -> List[Trade]:
        trades: List[Trade] = []
        now = time.time()
        for pos in positions:
            ticker = pos.get("ticker") or pos.get("market_ticker") or "unknown"
            pnl_cents = pos.get("pnl", 0)
            position_size = pos.get("position", pos.get("yes_position", 0))
            avg_price = pos.get("avg_price", pos.get("avg_entry_price", 0))
            pnl = round(pnl_cents / 100, 2) if isinstance(pnl_cents, (int, float)) else 0.0
            entry_price = float(avg_price) / 100 if avg_price else 0.0
            trades.append(
                Trade(
                    id=f"kalshi-{ticker}",
                    matchup=ticker,
                    team=str(pos.get("side", "yes")).upper(),
                    stake=float(position_size or 0),
                    entry_price=entry_price,
                    true_prob=entry_price,
                    edge=0.0,
                    result="PENDING",
                    pnl=pnl,
                    timestamp=now,
                )
            )
        return trades

    def _refresh_kalshi_account(self) -> None:
        if not self.kalshi_client:
            return
        try:
            balance = self.kalshi_client.get_balance()
            balance_cents = balance.get("balance") or balance.get("available") or 0
            self._bankroll = round(float(balance_cents) / 100, 2)
            if not self._initial_bankroll:
                self._initial_bankroll = self._bankroll
            self._total_pnl = round(self._bankroll - self._initial_bankroll, 2)
            positions = self.kalshi_client.get_positions()
            self._trades = self._convert_positions_to_trades(positions)
            if self.performance_tracker:
                self.performance_tracker.bulk_log(
                    [asdict(t) for t in self._trades],
                    source="actual",
                )
        except Exception as exc:  # pragma: no cover - network errors
            self._emit_log("WARNING", f"Kalshi sync failed: {exc}")

    def check_kalshi_connection(self) -> Dict[str, Any]:
        """Check if Kalshi API connection is working."""
        if not self.kalshi_client:
            return {"connected": False, "error": "Kalshi client not initialized"}
        try:
            balance = self.kalshi_client.get_balance()
            balance_cents = balance.get("balance") or balance.get("available") or 0
            balance_dollars = round(float(balance_cents) / 100, 2)
            self._emit_log("INFO", f"Kalshi uplink successful. Balance: ${balance_dollars:.2f}")
            return {
                "connected": True,
                "balance": balance_dollars,
                "message": "Kalshi API connected successfully"
            }
        except Exception as exc:
            self._emit_log("WARNING", f"Kalshi uplink failed: {exc}")
            return {"connected": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # BoltOdds Integration
    # ------------------------------------------------------------------
    def _init_boltodds_client(self) -> None:
        """Initialize BoltOdds client for sharp odds data."""
        api_key = self.config.get("boltodds_api_key", "")
        if not api_key:
            self._emit_log("WARNING", "BoltOdds API key not configured.")
            return
        
        sports = self.config.get("sports", ["NBA", "NFL", "NHL"])
        self.boltodds_client = BoltOddsClient(api_key=api_key, sports=sports)
        self._emit_log("INFO", f"BoltOdds client initialized for sports: {sports}")

    def _fetch_boltodds_games(self) -> Dict[str, Any]:
        """Fetch current games from BoltOdds."""
        if not self.boltodds_client:
            return {}
        try:
            return self.boltodds_client.fetch_games()
        except Exception as exc:
            self._emit_log("WARNING", f"BoltOdds games fetch failed: {exc}")
            return {}

    def _fetch_boltodds_markets(self) -> Dict[str, Any]:
        """Fetch current markets/odds from BoltOdds."""
        if not self.boltodds_client:
            return {}
        try:
            return self.boltodds_client.fetch_markets()
        except Exception as exc:
            self._emit_log("WARNING", f"BoltOdds markets fetch failed: {exc}")
            return {}

    def _parse_sharp_odds(self, games: Dict[str, Any], markets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse BoltOdds data to extract sharp odds (Pinnacle-style true probabilities).
        
        Returns list of opportunities with:
        - matchup: Game name
        - team: Team to bet on
        - sport: Sport category
        - sharp_prob: Sharp/true probability from BoltOdds
        - sharp_odds: American odds from sharp book
        """
        opportunities = []
        
        # BoltOdds returns games as dict with game_id -> game_info
        for game_key, game_info in games.items():
            if not isinstance(game_info, dict):
                continue
            
            sport = game_info.get("sport", "")
            matchup = game_info.get("game", game_key)
            universal_id = game_info.get("universal_id", "")
            
            # Filter by configured sports
            configured_sports = self.config.get("sports", [])
            if sport not in configured_sports:
                continue
            
            opportunities.append({
                "matchup": matchup,
                "sport": sport,
                "universal_id": universal_id,
                "game_time": game_info.get("when", ""),
            })
        
        return opportunities

    def _fetch_kalshi_sports_markets(self) -> List[Dict[str, Any]]:
        """Fetch sports markets from Kalshi."""
        if not self.kalshi_client:
            return []
        try:
            markets = self.kalshi_client.get_sports_markets()
            return [
                {
                    "ticker": m.ticker,
                    "title": m.title,
                    "subtitle": m.subtitle,
                    "yes_price": m.yes_price,
                    "no_price": m.no_price,
                    "volume": m.volume,
                    "category": m.category,
                }
                for m in markets
            ]
        except Exception as exc:
            self._emit_log("WARNING", f"Kalshi markets fetch failed: {exc}")
            return []

    def _find_opportunities(
        self,
        boltodds_games: List[Dict[str, Any]],
        kalshi_markets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Match BoltOdds sharp odds against Kalshi market prices to find +EV opportunities.
        
        An opportunity exists when:
        - Sharp probability > Kalshi implied probability (buy YES)
        - Sharp probability < Kalshi implied probability (buy NO)
        - Edge exceeds target_buy_ev threshold
        """
        opportunities = []
        target_ev = float(self.config.get("target_buy_ev", 0.05))
        min_prob = float(self.config.get("min_true_prob", 0.15))
        max_prob = float(self.config.get("max_true_prob", 0.85))
        
        # For now, emit available Kalshi markets as potential opportunities
        # Real matching would require team name normalization between platforms
        for market in kalshi_markets:
            yes_price = market.get("yes_price", 0)
            if yes_price <= 0:
                continue
            
            # Kalshi prices are in cents (0-100)
            market_prob = yes_price / 100.0
            
            # Skip if outside probability bounds
            if market_prob < min_prob or market_prob > max_prob:
                continue
            
            # For demo purposes, estimate a "sharp" probability with small edge
            # In production, this would come from matching BoltOdds games
            estimated_sharp_prob = market_prob  # Placeholder - no edge yet
            
            opp = {
                "matchup": market.get("title", market.get("ticker", "")),
                "team": market.get("subtitle", "YES"),
                "sport": market.get("category", "SPORTS"),
                "true_prob": estimated_sharp_prob,
                "market_prob": market_prob,
                "edge": (estimated_sharp_prob - market_prob) * 100,
                "kalshi_ticker": market.get("ticker"),
                "kalshi_yes_price": yes_price,
                "volume": market.get("volume", 0),
                "timestamp": time.time(),
            }
            
            # Calculate Kelly stake
            kelly_multiplier = float(self.config.get("kelly_multiplier", 0.5))
            if market_prob > 0 and estimated_sharp_prob > market_prob:
                kelly_fraction = max(
                    0.0,
                    ((estimated_sharp_prob * (1 / market_prob - 1)) - (1 - estimated_sharp_prob))
                    / (1 / market_prob - 1),
                )
                stake = self._bankroll * kelly_fraction * kelly_multiplier
                stake = min(stake, float(self.config.get("max_dollar_bet", 50)))
                stake = min(stake, self._bankroll * float(self.config.get("max_percentage_bet", 10)) / 100)
                opp["kelly_stake"] = max(0.0, stake)
            else:
                opp["kelly_stake"] = 0.0
            
            opportunities.append(opp)
        
        return opportunities

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _emit_log(self, level: str, message: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_line = f"[{ts}] {level} - {message}"
        self._log_queue.put(log_line)
        getattr(self.logger, level.lower(), self.logger.info)(message)
