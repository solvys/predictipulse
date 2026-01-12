# Coinbase Integration Handoff Prompt

## Project Context

You are working on **Predictipulse**, an automated sports betting system that identifies arbitrage opportunities between sharp sportsbooks (via BoltOdds) and prediction markets (currently Kalshi). The system includes:

- **Backend**: Flask app (`app.py`) with real-time opportunity scanning
- **Frontend**: Modern dashboard with live feeds, backtesting, and configuration
- **Current Integrations**: 
  - Kalshi (prediction market) - see `kalshi_adapter.py`
  - BoltOdds (sharp sportsbook odds) - see `boltodds_adapter.py`
  - ESPN (historical data for backtesting) - see `espn_adapter.py`

## Task: Integrate Coinbase Prediction Markets

### Requirements

1. **Coinbase Prediction Markets Data Integration**
   - Fetch prediction market data from Coinbase
   - Integrate with existing opportunity matching logic
   - Display Coinbase markets alongside Kalshi opportunities

2. **Coinbase Account Card**
   - Create a new account card similar to the "Kalshi Tracker" card
   - Display account balance, P&L, and connection status
   - Add trading capabilities (buy/sell positions)
   - Include an "Uplink" button to check connection status

3. **UI/UX Requirements**
   - Follow existing design patterns (see `templates/components/header.html` for Kalshi Tracker reference)
   - Use the same styling system (`static/styles.css`)
   - Match the visual style: dark theme, gold accent color (`#d4af37`), liquid glass effects
   - Add the Coinbase card to the dashboard header area (alongside Kalshi Tracker)

### Technical Implementation Guide

#### 1. Create Coinbase Adapter (`coinbase_adapter.py`)

Follow the pattern from `kalshi_adapter.py`:
- Create a `CoinbaseClient` class
- Implement authentication (API key or OAuth)
- Methods needed:
  - `get_account()` - Get account balance and info
  - `get_markets()` - Fetch available prediction markets
  - `get_market_prices(ticker)` - Get current prices for a market
  - `place_order(ticker, side, size, price)` - Execute trades
  - `get_positions()` - Get current open positions
  - `get_trades()` - Get trade history

**Reference**: Check Coinbase Advanced Trade API documentation for prediction markets endpoints.

#### 2. Update Configuration

- Add Coinbase API credentials to `config.json` (similar to `boltodds_api_key`)
- Update `config_manager.py` to handle Coinbase settings
- Add Coinbase-specific config options (if needed)

#### 3. Integrate with Predictipulse Engine

In `predictipulse_engine.py`:
- Initialize `CoinbaseClient` similar to how `BoltOddsClient` is initialized
- Add methods to fetch Coinbase markets and compare with BoltOdds odds
- Integrate Coinbase opportunities into the existing opportunity matching logic
- Add Coinbase trades to the trade stream

#### 4. Update Flask Routes (`app.py`)

Add new API endpoints:
- `GET /api/coinbase/account` - Get account info
- `GET /api/coinbase/markets` - Get available markets
- `POST /api/coinbase/uplink` - Check connection status
- `POST /api/coinbase/trade` - Execute a trade
- `GET /api/coinbase/positions` - Get open positions
- `GET /api/coinbase/trades` - Get trade history

#### 5. Frontend Components

**Create `templates/components/coinbase_tracker.html`**:
- Similar structure to Kalshi Tracker
- Display account balance, P&L, connection status
- "Uplink" button with status pill
- Start/Stop engine button (if applicable)

**Update `templates/index.html`**:
- Add Coinbase tracker to header area
- Add Coinbase opportunities to opportunities feed
- Add Coinbase trades to trades table
- Update JavaScript to handle Coinbase data streams

**Update `templates/components/header.html`**:
- Add Coinbase tracker card alongside Kalshi Tracker

#### 6. Styling

Update `static/styles.css`:
- Add Coinbase-specific styles if needed
- Ensure consistent styling with existing components
- Use existing color scheme and design patterns

### Code Patterns to Follow

1. **Adapter Pattern**: Follow `kalshi_adapter.py` structure
   - Use dataclasses for market/order objects
   - Implement proper error handling
   - Add logging for debugging
   - Handle rate limiting and retries

2. **API Integration**: Follow `boltodds_adapter.py` patterns
   - Use async/await for WebSocket connections (if applicable)
   - Implement reconnection logic
   - Handle authentication properly

3. **Frontend**: Follow existing component patterns
   - Use Server-Sent Events (SSE) for real-time updates
   - Follow existing JavaScript patterns in `templates/index.html`
   - Use the same formatting utilities (`fmt.currency`, `fmt.pct`)

### Key Files to Reference

- `kalshi_adapter.py` - Reference for prediction market adapter
- `boltodds_adapter.py` - Reference for data source adapter
- `app.py` - Flask routes and SSE streams
- `predictipulse_engine.py` - Core opportunity matching logic
- `templates/components/header.html` - Kalshi Tracker UI reference
- `templates/index.html` - JavaScript patterns and SSE handling
- `static/styles.css` - Styling patterns

### Testing Checklist

- [ ] Coinbase API authentication works
- [ ] Can fetch account balance and info
- [ ] Can fetch prediction markets
- [ ] Can get market prices
- [ ] Can place orders (buy/sell)
- [ ] Can get positions and trade history
- [ ] Coinbase card displays correctly in header
- [ ] Uplink status check works
- [ ] Opportunities from Coinbase appear in feed
- [ ] Trades from Coinbase appear in trades table
- [ ] Styling matches existing design
- [ ] No JavaScript errors in console
- [ ] All API endpoints return correct data

### Important Notes

- **Security**: Never commit API keys or credentials. Use `config.json` (gitignored) or environment variables
- **Error Handling**: Implement robust error handling for API failures
- **Rate Limiting**: Respect Coinbase API rate limits
- **Testing**: Test with paper trading/sandbox mode first if available
- **Documentation**: Reference official Coinbase API documentation for endpoints and authentication

### Current Branch

Work on branch: `v.1.12.3`

### Questions to Resolve

1. Does Coinbase have a prediction markets API, or is this for a different product?
2. What authentication method does Coinbase use (API key, OAuth, etc.)?
3. Are there any specific market types or filters needed?
4. Should Coinbase trades be integrated into the same opportunity matching logic, or separate?

---

**Start by researching the Coinbase API documentation for prediction markets, then create the adapter following the patterns established in the codebase.**
