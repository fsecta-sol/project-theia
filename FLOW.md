# Project Theia - Smart Money Wallet Following Pipeline

## Overview
Theia adalah paper-trading agent untuk pasar memecoin Solana yang mengikuti
wallet-wallet "smart money" yang terverifikasi profitable. Pipeline menggunakan
timing-latency-tolerant approach: masuk 25-35 menit setelah wallet target beli,
menyesuaikan dengan timing backtest (T+30m simulated entry).

## Architecture Flow

### 1. Wallet Discovery & Profiling (`theia-wallet-discovery`)
- **Schedule**: `0 */6 * * *` (every 6 hours)
- **Source**: GMGN.ai leaderboard (winrate + PnL distribution, not volume-ranked)
- **Process**:
  - Scrape GMGN leaderboard (30d PnL, winrate, tags)
  - Filter: exclude `wash_trader`, `bot` tags
  - Profile: analyze 30d transaction history
  - Latency-tolerance test: split buys into train/test (50/50), simulate T+30m entry
  - Flag `is_smart_money=1` only if test window clears (n>=5, expectancy>0)

### 2. Signal Capture & Paper Trading (`theia-wallet-pipeline`)
- **Schedule**: `*/5 * * * *` (every 5 minutes)
- **Process**:
  - Poll all `is_smart_money=1` wallets via `chainrpc.wallet_swaps()`
  - Track new buy signals within **T+25m to T+35m window** (ketat, match backtest timing)
  - Screen: liquidity >=$5k, price cap <=1.5x wallet entry price
  - Deduplicate: prevent multiple entries per mint
  - Per-wallet cap: max 3 open positions per tracked wallet
  - Open PAPER trade with simulated entry fill (gas + slippage estimated)

### 3. Position Monitoring & Exit (`theia-wallet-monitor`)
- **Schedule**: `*/5 * * * *` (every 5 minutes)
- **Process**:
  - Check all open paper positions
  - Apply `exit_engine` with parameters:
    - Hard stop: -35%
    - Trailing stop: 25% drop from ATH
    - Take profit ladder: 50% @ 2x, 50% @ 4x
    - **Time stop: 60 minutes** (updated from 30min per M-04 finding)
  - Close position with simulated exit fills
  - Calculate PnL via `pnl.fifo_trade_pnls()` (includes gas + slippage)

### 4. Daily Reporting (`theia-wallet-report`)
- **Schedule**: `0 7 * * *` (daily 07:00)
- **Process**: format and deliver digest of pipeline performance

### 5. Health Monitoring (`theia-pipeline-health`)
- **Schedule**: `*/5 * * * *` (every 5 minutes)
- **Process**: read-only health checks (no state changes)

## Key Timing Changes (vs v2)

### Before (buggy):
- Pipeline entered ASAP within 30-minute window
- Cron ran every 10 minutes → 3x hits per signal = API waste
- Backtest assumed T+30m entry, live entered T+2, T+10, T+20 → mismatch

### After (fixed):
- Pipeline enters only within **T+25m to T+35m window** (ketat)
- Cron runs every 5 minutes → precise timing alignment
- Backtest and live now match: both T+30m equivalent timing
- Time stop extended from 30min to 60min (proved better in M-04)

## Safety Mechanisms
- **Screening veto**: low liquidity, price cap, honeypot detection
- **Per-wallet exposure limits**: max 3 open positions per smart wallet
- **Deduplication**: prevent multiple entries per token
- **Paper-only**: no real funds, simulated fills with realistic gas/slippage

## Data Sources
- **GMGN.ai**: smart wallet discovery (PnL, winrate, tags)
- **Helius RPC**: wallet transaction history
- **DexScreener**: pool data (price, liquidity, volume)
- **Gecko OHLCV**: forward price action for exit simulation
- **Local SQLite**: persistence (signals, trades, profiles, PnL)

## Cron Configuration
All jobs are `no_agent: true` to minimize LLM token usage:
- `theia-wallet-discovery`: `0 */6 * * *`, no_agent=true
- `theia-wallet-pipeline`: `*/5 * * * *`, no_agent=true  
- `theia-wallet-monitor`: `*/5 * * * *`, no_agent=true
- `theia-wallet-report`: `0 7 * * *`, no_agent=true
- `theia-pipeline-health`: `*/5 * * * *`, no_agent=true
- `theia-task-runner`: `*/1 * * * *`, no_agent=true

## Success Metrics
Target: **expectancy > 0 AND profit_factor > 1**, net of latency + fees
- Measured via paper trading PnL (fifo accounting)
- Forward validation: out-of-sample performance on unseen tokens
- Risk management: stop losses, position sizing, diversification