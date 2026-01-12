"""
Kalshi API Adapter for Predictipulse

Kalshi is a CFTC-regulated prediction market legal for US customers.
API Docs: https://docs.kalshi.com/

IMPORTANT LIMITATIONS:
- Kalshi's sports markets are LIMITED compared to Polymarket
- Most Kalshi markets are props/futures, not game moneylines
- Direct Pinnacle arbitrage may not always be possible
- This adapter provides the framework; market availability varies

Usage:
    from kalshi_adapter import KalshiClient
    
    client = KalshiClient(email="your@email.com", password="your_password")
    # OR with API key:
    client = KalshiClient(api_key="your_api_key")
    
    markets = client.get_sports_markets()
    client.place_order(ticker="SPORTSTEAM-25JAN12", side="yes", price=55, count=10)
"""

import hashlib
import os
import socket
import time
from pathlib import Path
import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import requests

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


@dataclass
class KalshiMarket:
    ticker: str
    title: str
    subtitle: str
    yes_price: float  # 0-100 (cents)
    no_price: float
    volume: int
    open_interest: int
    close_time: str
    status: str
    category: str


@dataclass
class KalshiOrder:
    order_id: str
    ticker: str
    side: str  # "yes" or "no"
    price: int  # cents (1-99)
    count: int  # number of contracts
    status: str


class KalshiClient:
    """
    Kalshi API Client
    
    Supports both email/password login and API key authentication.
    API keys are recommended for automated trading.
    
    Get your API key at: https://kalshi.com/account/api
    """
    
    # Per Kalshi docs (production): https://api.elections.kalshi.com/trade-api/v2
    # Demo environment: https://demo-api.kalshi.co/trade-api/v2
    #
    # You can override the selected base URL with env var:
    #   KALSHI_BASE_URL="https://api.elections.kalshi.com/trade-api/v2"
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"  # For paper trading

    PROD_URL_CANDIDATES = [
        "https://api.elections.kalshi.com/trade-api/v2",
        # Legacy/alternate host some users may have configured historically:
        "https://api.kalshi.com/trade-api/v2",
    ]
    DEMO_URL_CANDIDATES = [
        "https://demo-api.kalshi.co/trade-api/v2",
    ]
    
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_secret_path: Optional[str] = None,
        demo: bool = False,
    ):
        # Choose base URL:
        # - explicit env override wins
        # - otherwise pick the first hostname that resolves
        env_base_url = (os.environ.get("KALSHI_BASE_URL") or "").strip()
        if env_base_url:
            self.base_url = env_base_url.rstrip("/")
        else:
            candidates = self.DEMO_URL_CANDIDATES if demo else self.PROD_URL_CANDIDATES
            self.base_url = self._select_base_url(candidates)
        self.email = email
        self.password = password
        self.api_key = api_key
        self.api_secret = api_secret
        if api_secret_path and not api_secret:
            try:
                self.api_secret = Path(api_secret_path).read_text().strip()
            except FileNotFoundError as exc:
                raise ValueError(f"API secret file not found at {api_secret_path}") from exc
        self.token: Optional[str] = None
        self.token_expiry: float = 0
        self.member_id: Optional[str] = None
        
        if api_key and (self.api_secret is not None):
            self._auth_method = "api_key"
        elif email and password:
            self._auth_method = "password"
        else:
            raise ValueError("Provide either (api_key, api_secret) or (email, password)")

    @staticmethod
    def _host_resolves(base_url: str) -> bool:
        """Return True if the hostname in base_url resolves via DNS."""
        host = urlparse(base_url).hostname
        if not host:
            return False
        try:
            socket.getaddrinfo(host, 443)
            return True
        except socket.gaierror:
            return False

    @classmethod
    def _select_base_url(cls, candidates: List[str]) -> str:
        """Pick the first candidate whose hostname resolves. Raise a helpful error if none do."""
        for c in candidates:
            if cls._host_resolves(c):
                return c.rstrip("/")

        # None resolved: raise an actionable error
        hosts = [urlparse(c).hostname for c in candidates]
        hosts_str = ", ".join([h for h in hosts if h])
        raise ConnectionError(
            "Kalshi API hostname could not be resolved via DNS. "
            f"Tried: {hosts_str}. "
            "This is a network/DNS issue (not an API key issue). "
            "You can override with KALSHI_BASE_URL if you have a custom endpoint."
        )
    
    def _get_headers(self, method: str = "GET", path: str = "") -> Dict[str, str]:
        """Generate authentication headers."""
        headers = {"Content-Type": "application/json"}
        
        if self._auth_method == "api_key":
            # RSA-PSS signature authentication
            timestamp = str(int(time.time() * 1000))
            # Kalshi signs the request path including the /trade-api/v2 prefix.
            # Our client stores that prefix in base_url, so we must include it here.
            base_path = (urlparse(self.base_url).path or "").rstrip("/")
            signing_path = f"{base_path}{path}" if base_path else path
            msg_string = f"{timestamp}{method}{signing_path}"
            
            if HAS_CRYPTO and self.api_secret:
                # Load the private key from PEM
                private_key = serialization.load_pem_private_key(
                    self.api_secret.encode(),
                    password=None,
                    backend=default_backend()
                )
                # Sign with RSA-PSS (Kalshi's required format)
                signature_bytes = private_key.sign(
                    msg_string.encode(),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                signature = base64.b64encode(signature_bytes).decode()
            else:
                # Fallback if cryptography not available
                signature = base64.b64encode(
                    hashlib.sha256(msg_string.encode()).digest()
                ).decode()
            
            headers["KALSHI-ACCESS-KEY"] = self.api_key
            headers["KALSHI-ACCESS-SIGNATURE"] = signature
            headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp
        else:
            # Token-based auth
            if time.time() > self.token_expiry - 60:  # Refresh 1 min before expiry
                self._login()
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def _login(self) -> None:
        """Login with email/password to get token."""
        resp = requests.post(
            f"{self.base_url}/login",
            json={"email": self.email, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["token"]
        self.member_id = data["member_id"]
        # Tokens expire in 30 minutes
        self.token_expiry = time.time() + 1800
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make authenticated API request."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(method, endpoint)
        
        resp = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_data,
        )
        resp.raise_for_status()
        return resp.json()
    
    # -------------------------------------------------------------------------
    # Market Data (Public endpoints - no auth needed for basic data)
    # -------------------------------------------------------------------------
    
    def get_events(
        self,
        series_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get events (groups of related markets).
        
        Args:
            series_ticker: Filter by series (e.g., "SPORTS", "NFL")
            status: "open", "closed", or "settled"
            limit: Max results
        """
        params = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        
        return self._request("GET", "/events", params=params).get("events", [])
    
    def get_markets(
        self,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get individual markets.
        
        Args:
            event_ticker: Filter by specific event
            series_ticker: Filter by series
            status: Market status
            limit: Max results
        """
        params = {"status": status, "limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        
        return self._request("GET", "/markets", params=params).get("markets", [])
    
    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Get a specific market by ticker."""
        return self._request("GET", f"/markets/{ticker}").get("market", {})
    
    def get_orderbook(self, ticker: str, depth: int = 10) -> Dict[str, Any]:
        """
        Get orderbook for a market.
        
        Returns:
            {
                "yes": [[price, size], ...],  # Bids for YES
                "no": [[price, size], ...],   # Bids for NO
            }
        """
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})
    
    def get_sports_markets(self) -> List[KalshiMarket]:
        """
        Get all open sports-related markets.
        
        Note: Kalshi's sports offerings are limited. Common series include:
        - NFL playoffs/Super Bowl
        - NBA playoffs
        - MLB World Series
        - Player props (points, touchdowns, etc.)
        """
        # Try to find sports-related series
        sports_keywords = ["NFL", "NBA", "MLB", "NHL", "SPORTS", "SUPER", "PLAYOFF"]
        all_markets = []
        
        events = self.get_events(status="open", limit=200)
        for event in events:
            # Check if event title contains sports keywords
            title = event.get("title", "").upper()
            if any(kw in title for kw in sports_keywords):
                event_markets = self.get_markets(event_ticker=event["event_ticker"])
                for m in event_markets:
                    all_markets.append(
                        KalshiMarket(
                            ticker=m["ticker"],
                            title=m.get("title", ""),
                            subtitle=m.get("subtitle", ""),
                            yes_price=m.get("yes_ask", 0),
                            no_price=m.get("no_ask", 0),
                            volume=m.get("volume", 0),
                            open_interest=m.get("open_interest", 0),
                            close_time=m.get("close_time", ""),
                            status=m.get("status", ""),
                            category=event.get("category", ""),
                        )
                    )
        
        return all_markets
    
    # -------------------------------------------------------------------------
    # Trading (Authenticated endpoints)
    # -------------------------------------------------------------------------
    
    def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        return self._request("GET", "/portfolio/balance")
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        return self._request("GET", "/portfolio/positions").get("market_positions", [])
    
    def place_order(
        self,
        ticker: str,
        side: str,  # "yes" or "no"
        price: int,  # cents 1-99
        count: int,  # number of contracts
        order_type: str = "limit",  # "limit" or "market"
        action: str = "buy",  # "buy" or "sell"
    ) -> KalshiOrder:
        """
        Place an order.
        
        Args:
            ticker: Market ticker (e.g., "KXNFLSB-25FEB09")
            side: "yes" or "no"
            price: Price in cents (1-99)
            count: Number of contracts
            order_type: "limit" or "market"
            action: "buy" or "sell"
        
        Returns:
            KalshiOrder with order details
        """
        order_data = {
            "ticker": ticker,
            "side": side,
            "type": order_type,
            "action": action,
            "count": count,
        }
        if order_type == "limit":
            order_data["yes_price" if side == "yes" else "no_price"] = price
        
        resp = self._request("POST", "/portfolio/orders", json_data=order_data)
        order = resp.get("order", {})
        
        return KalshiOrder(
            order_id=order.get("order_id", ""),
            ticker=ticker,
            side=side,
            price=price,
            count=count,
            status=order.get("status", ""),
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            self._request("DELETE", f"/portfolio/orders/{order_id}")
            return True
        except Exception:
            return False
    
    def get_orders(self, status: str = "resting") -> List[Dict[str, Any]]:
        """Get orders by status: 'resting', 'pending', 'executed', 'canceled'."""
        return self._request("GET", "/portfolio/orders", params={"status": status}).get("orders", [])


# -----------------------------------------------------------------------------
# PolyPulse Integration Helper
# -----------------------------------------------------------------------------

def find_arbitrage_opportunities(
    kalshi_client: KalshiClient,
    pinnacle_odds: Dict[str, float],  # {team_name: true_probability}
    min_edge: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Find arbitrage opportunities between Kalshi and Pinnacle.
    
    This is a simplified example - real implementation would need:
    1. Better team/event matching between platforms
    2. Handling of different market types (moneyline vs props)
    3. Consideration of Kalshi's fee structure
    
    Args:
        kalshi_client: Authenticated Kalshi client
        pinnacle_odds: Dict mapping team names to true probabilities
        min_edge: Minimum edge required (default 5%)
    
    Returns:
        List of opportunity dicts
    """
    opportunities = []
    
    markets = kalshi_client.get_sports_markets()
    
    for market in markets:
        # Try to match market to Pinnacle odds
        # This is simplified - real matching would be more complex
        market_title = market.title.lower()
        
        for team, true_prob in pinnacle_odds.items():
            if team.lower() in market_title:
                kalshi_price = market.yes_price / 100  # Convert cents to probability
                edge = true_prob - kalshi_price
                
                if edge >= min_edge:
                    opportunities.append({
                        "ticker": market.ticker,
                        "title": market.title,
                        "team": team,
                        "kalshi_price": kalshi_price,
                        "true_prob": true_prob,
                        "edge": edge,
                        "volume": market.volume,
                    })
    
    return opportunities


# -----------------------------------------------------------------------------
# Example Usage
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Demo mode - no real money
    print("Kalshi Adapter - Demo Mode")
    print("=" * 50)
    
    # Note: You'd need real credentials here
    # client = KalshiClient(
    #     api_key="your_api_key",
    #     api_secret="your_api_secret",
    #     demo=True,  # Use demo environment
    # )
    
    print("""
To use Kalshi with Gambot:

1. Create account at https://kalshi.com
2. Get API key at https://kalshi.com/account/api
3. Set up credentials:
   
   client = KalshiClient(
       api_key="YOUR_KEY",
       api_secret="YOUR_SECRET",
       demo=True,  # Start with demo mode!
   )

4. Find sports markets:
   
   markets = client.get_sports_markets()
   for m in markets:
       print(f"{m.ticker}: {m.title} @ {m.yes_price}¢")

5. Place orders:
   
   order = client.place_order(
       ticker="KXNFLSB-25FEB09",
       side="yes",
       price=55,  # 55 cents = 55% implied probability
       count=10,  # 10 contracts
   )

IMPORTANT CAVEATS:
- Kalshi fees: ~7¢ per contract + settlement fees
- Sports markets are LIMITED - mostly futures/props, not game moneylines
- Liquidity can be thin on smaller markets
- API rate limits apply
""")
