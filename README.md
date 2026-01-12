# Predictipulse: Automated Sports Betting on Kalshi

## Overview
Predictipulse is an open-source trading bot that identifies profitable sports betting opportunities and executes them on [Kalshi](https://kalshi.com/). By pulling market data from sharp sportsbooks and comparing against Kalshi, Predictipulse leverages a probabilistic modeling approach and Kelly Criterion bet sizing to pursue long-term capital growth.

## Introduction
Sports betting markets often present mispriced odds. Sharp sportsbooks are generally efficient at pricing, so comparing their implied probability to that of Kalshi can reveal edges. Predictipulse automates this comparison and calculates stake sizes through the Kelly Criterion to optimize growth over time.

## Key Features
- **Automated Market Scanning**: Constantly checks Kalshi odds against sharp sportsbook lines to detect profitable divergences.
- **Probability Modeling**: Estimates true event probabilities, searching for positive expected value (EV).
- **Kelly Criterion Bet Sizing**: Dynamically adjusts stake sizes to maximize growth while controlling risk.
- **Real-time Dashboard**: Modern web-based control panel with live P&L tracking, opportunity feeds, and trade history.

## How It Works
1. **Data Collection**: Predictipulse queries BoltOdds for sharp odds, then retrieves Kalshi prices in real time.
2. **Probability Estimation**: By comparing implied probabilities, Predictipulse flags situations where Kalshi's market prices differ significantly from the baseline "true" odds.
3. **Kelly Criterion Calculation**: Once an opportunity is found, the bot calculates the optimal stake size using Kelly Criterion formulas—adjustable for risk tolerance—to aim for long-term growth.
4. **Order Execution**: Predictipulse sends orders when placing trades on Kalshi.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Credentials
Create a `kalshi_keys.csv` file with your Kalshi API credentials:
```csv
api_key,api_secret
"YOUR_API_KEY","YOUR_PRIVATE_KEY"
```

### 3. Launch Predictipulse
Double-click `Predictipulse.command` or run:
```bash
python3 app.py
```

Then open http://localhost:3000 in your browser.

## Configuration Parameters
- **Kelly Multiplier**: Scales the Kelly optimal bet size (0-1). Lower values reduce volatility.
- **Target Buy EV**: Minimum edge required before placing a buy bet (e.g., 0.05 = 5% edge).
- **Target Sell EV**: Minimum edge required before selling a position.
- **Max % Bet**: Maximum percentage of bankroll for any single bet.
- **Max $ Bet**: Maximum dollar amount for any individual bet.
- **Min/Max True Prob**: Probability range for bets to avoid extreme favorites/underdogs.

## Dashboard Features
- **Cumulative P&L Chart**: Track your performance with 24h and 7d views
- **Kalshi Tracker**: Real-time balance, uplink status, and engine control
- **Live Opportunities**: Real-time feed of detected arbitrage opportunities
- **Recent Trades**: History of all executed trades with results
- **Configuration Panel**: Adjust all trading parameters on the fly

---

**Thank you for choosing Predictipulse! Bet responsibly, manage your risk carefully, and enjoy the process of systematic sports trading.**
