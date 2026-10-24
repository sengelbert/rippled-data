# rippled-data

Fast, zero-infrastructure Python CLI and interactive Streamlit dashboard for analyzing XRP Ledger (XRPL) Rich-List percentile brackets, wallet wealth percentiles, balance tier distributions, global supply metrics, and top whale/entity holdings.

Instead of deploying dedicated `rippled` nodes on AWS/Docker and sequentially paginating through millions of raw ledger objects, this project queries public XRPL indexer APIs (**Rich-List.info**, **XRPSCAN**, and **public XRPL JSON-RPC**) concurrently using `asyncio` and `httpx`—completing in **~2 seconds**.

For architectural background and design rationale, see the [Architecture Decision Records (`docs/DECISIONS.md`)](file:///home/simon/Code/Personal/rippled-data/docs/DECISIONS.md).

---

## Features

- **Wallet Wealth Percentile & Rank Lookup**: Search any XRPL wallet (`r...`) to get its exact global rank (out of ~8.26M+ wallets), wealth percentile (`99.9999%` / `Top 0.0001%`), current Rich-List bracket, exact XRP needed to reach the next percentile tier, active escrow unlock schedule, and on-ledger metadata (entity label, inception date, activating parent wallet, owner count).
- **Global Supply & Ledger Summary**: Validated ledger index, close time, active account count, 100B max supply, burned XRP, liquid circulating XRP in wallets, and XRP locked in escrow.
- **Rich-List Percentile Brackets**: Exact account counts and XRP balance ranges across the 10 classic tiers (`Top 0.01%` / `100% - 99.99%` down to `Top 10%` / `95% - 90%`).
- **Whale Concentration & Balance Tiers**: Supply concentration across the `Top 10` to `Top 10,000` accounts and full ledger distribution across 18 XRP balance tiers (`1B+ XRP` down to `0 - 20 XRP`).
- **Entity & Top Holder Attribution**: Ranks top accounts and aggregates known institutional/exchange entities (`Ripple`, `UPbit`, `Coinbase`, `Binance`, `Robinhood`, `Bithumb`, `Uphold`, `Kraken`, etc.) across both **Liquid XRP** and **Escrowed XRP**.
- **90-Day Whale Flow Event Study & Strategy Backtest ([`src/whale_flow_study.py`](file:///home/simon/Code/Personal/rippled-data/src/whale_flow_study.py))**: Pulls 90 days of ledger-wide `Payment >= 1,000,000 XRP` transactions via XRPSCAN's SQL API alongside 1H `XRP/USD` OHLCV candles, separates internal custody noise from true exchange inflows/outflows, and evaluates both forward return regimes and a 3-way strategy backtest (Baseline Breakout vs. On-Chain Flow-Gated Breakout vs. Standalone Flow).

---

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## 📊 Live Web Dashboard (Streamlit)

`rippled-data` includes an internal Streamlit web dashboard ([`src/dashboard.py`](file:///home/simon/Code/Personal/rippled-data/src/dashboard.py)) running on port **`8502`**:

- **Access**: Open `http://localhost:8502` or `http://192.168.0.4:8502` in any browser on the local network.
- **Service Management (Systemd)**:
  The unit template is version-controlled in [`rippled-dashboard.service`](file:///home/simon/Code/Personal/rippled-data/rippled-dashboard.service) and installed at `~/.config/systemd/user/rippled-dashboard.service`:
  ```bash
  systemctl --user status rippled-dashboard.service    # Check dashboard service status
  systemctl --user restart rippled-dashboard.service   # Restart dashboard service
  journalctl --user -f -u rippled-dashboard.service    # View live dashboard logs
  ```
- **Manual Run**:
  ```bash
  .venv/bin/streamlit run src/dashboard.py --server.port 8502
  ```

---

## 💻 CLI Usage

Run the analytics report directly in the terminal via [`src/xrpl_analytics.py`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py):

```bash
.venv/bin/python src/xrpl_analytics.py
```

### CLI Options

```text
Options:
  -t, --top INTEGER     Number of top accounts and entities to display. [default: 15]
  -a, --account TEXT    Look up rank and balance details for a specific XRPL address.
  -s, --save            Save raw API snapshot to data/<ledger_index>_snapshot.json.
  -f, --from-file PATH  Load raw snapshot from a local JSON file instead of querying APIs.
  --json-output         Output structured analytics as JSON.
  --help                Show this message and exit.
```

### Examples

```bash
# Show top 10 accounts & entities and save a local snapshot to data/
.venv/bin/python src/xrpl_analytics.py --top 10 --save

# Look up a specific XRPL account's rank, wealth percentile, and entity info
.venv/bin/python src/xrpl_analytics.py --account rPyCQm8E5j78PDbrfKF24fRC7qUAk1kDMZ

# Re-run analysis offline from a saved snapshot
.venv/bin/python src/xrpl_analytics.py --from-file data/ledger_107855218_snapshot.json

# Run the 90-day XRPL whale transaction event study & strategy backtest
.venv/bin/python src/whale_flow_study.py --days 90 --min-xrp 1000000
```

---

## Sample CLI Output

```text
#### Ledger & Supply Data ####
Ledger Index:       107,855,218
Close Time:         2026-10-23T19:00:10.000Z
Total Accounts:     8,260,854
Max Supply:         100,000,000,000.00 XRP
Total Remaining:    99,985,585,497.60 XRP (Burned: 14,414,572.90 XRP)
Liquid in Wallets:  68,450,253,712.73 XRP (68.46%)
Locked in Escrow:   31,535,331,784.87 XRP (31.54%)
Average Balance:    8,286.10 XRP / account

#### Account Percentile Brackets (Rich List) ####
Top 100% - 99.99% (Top 0.01%): Total Accounts:     827 out of 8,260,854 (    827 inclusive) | Balance Range: 1,851,639,906.28 - 3,722,982.10 XRP
Top 99.99% - 99.9% (Top 0.1% ): Total Accounts:   8,261 out of 8,260,854 (  7,434 inclusive) | Balance Range:     3,722,982.10 -   272,419.73 XRP
Top 99.9% - 99.8% (Top 0.2% ): Total Accounts:  16,522 out of 8,260,854 (  8,261 inclusive) | Balance Range:       272,419.73 -   154,874.90 XRP
Top 99.8% - 99.5% (Top 0.5% ): Total Accounts:  41,305 out of 8,260,854 ( 24,783 inclusive) | Balance Range:       154,874.90 -    78,959.67 XRP
Top 99.5% - 99% (Top 1%   ): Total Accounts:  82,609 out of 8,260,854 ( 41,304 inclusive) | Balance Range:        78,959.67 -    43,493.33 XRP
Top 99% - 98% (Top 2%   ): Total Accounts: 165,218 out of 8,260,854 ( 82,609 inclusive) | Balance Range:        43,493.33 -    21,309.24 XRP
Top 98% - 97% (Top 3%   ): Total Accounts: 247,826 out of 8,260,854 ( 82,608 inclusive) | Balance Range:        21,309.24 -    13,655.00 XRP
Top 97% - 96% (Top 4%   ): Total Accounts: 330,435 out of 8,260,854 ( 82,609 inclusive) | Balance Range:        13,655.00 -    10,005.68 XRP
Top 96% - 95% (Top 5%   ): Total Accounts: 413,043 out of 8,260,854 ( 82,608 inclusive) | Balance Range:        10,005.68 -     7,248.18 XRP
Top 95% - 90% (Top 10%  ): Total Accounts: 826,086 out of 8,260,854 (413,043 inclusive) | Balance Range:         7,248.18 -     2,068.35 XRP
```

---

## Running Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```
