#!/usr/bin/env python3
"""90-Day XRPL Whale Flow Event Study & Strategy Backtest (Phase 1 Experiment).

Fetches 90 days of ledger-wide XRPL Payment transactions (>= 1,000,000 XRP) via
XRPSCAN's SQL API alongside 90 days of 1-Hour XRP/USD OHLCV candles, classifies
labeled exchange inflows/outflows vs. internal custody noise, and evaluates:
1. Forward 4H / 12H / 24H XRP/USD returns after Net Flow Z-score extremes.
2. Strategy A/B/C Backtest:
   - Baseline Price-Action Breakout (24H Donchian + ATR/Trailing stop)
   - On-Chain Flow-Gated Breakout (blocks entries during heavy exchange inflows)
   - Standalone On-Chain Flow Trading (trading pure flow spikes without price action)
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

import click
import httpx
import pandas as pd

XRPSCAN_BASE_URL = "https://api.xrpscan.com/api/v1"
XRPSCAN_SQL_URL = "https://console.xrpscan.com/api/v1/sql"
BINANCE_KLINES_URL = "https://api.binance.us/api/v3/klines"

EXCHANGE_KEYWORDS = {
    "binance",
    "upbit",
    "coinbase",
    "bithumb",
    "kraken",
    "robinhood",
    "bitstamp",
    "uphold",
    "bybit",
    "okx",
    "bitfinex",
    "bitget",
    "bitso",
    "bitvavo",
    "coinone",
    "korbit",
    "kucoin",
    "gate.io",
    "htx",
    "huobi",
    "mexc",
    "crypto.com",
    "gemini",
    "luno",
    "indodax",
    "bitbank",
    "liquid",
    "paribu",
    "btcturk",
    "gopax",
    "ceffu",
    "bitgo",
    "copper",
}

RIPPLE_KEYWORDS = {
    "ripple",
    "chrislarsen",
    "ahbritto",
}


def classify_entity_role(entity_name: str | None) -> str:
    """Classify an XRPSCAN entity name into EXCHANGE, RIPPLE, KNOWN_OTHER, or UNLABELED."""
    if not entity_name or entity_name == "Unlabeled":
        return "UNLABELED"
    lower = entity_name.lower()
    if any(k in lower for k in RIPPLE_KEYWORDS):
        return "RIPPLE"
    if any(k in lower for k in EXCHANGE_KEYWORDS):
        return "EXCHANGE"
    return "KNOWN_OTHER"


def classify_whale_payment(
    src_role: str,
    dst_role: str,
    src_entity: str,
    dst_entity: str,
    has_dest_tag: bool,
) -> str:
    """Classify a >=1M XRP Payment into flow categories.

    Returns one of:
      - 'EXCHANGE_INFLOW'     (Bearish supply added to exchange)
      - 'EXCHANGE_OUTFLOW'    (Bullish withdrawal from exchange to private wallet)
      - 'INTERNAL_NOISE'      (Exchange <-> Exchange or Ripple <-> Ripple sweep)
      - 'WHALE_TRANSFER'      (Unlabeled <-> Unlabeled OTC / custody transfer)
    """
    # Internal sweep between same entity or between two exchanges / Ripple wallets
    if src_entity != "Unlabeled" and src_entity == dst_entity:
        return "INTERNAL_NOISE"
    if src_role == "EXCHANGE" and dst_role == "EXCHANGE":
        return "INTERNAL_NOISE"
    if src_role == "RIPPLE" and dst_role == "RIPPLE":
        return "INTERNAL_NOISE"

    # Deposits into a labeled exchange from an unlabeled whale or Ripple treasury
    if dst_role == "EXCHANGE" and src_role in ("UNLABELED", "RIPPLE", "KNOWN_OTHER"):
        return "EXCHANGE_INFLOW"

    # Withdrawals from a labeled exchange to an unlabeled self-custody wallet
    if src_role == "EXCHANGE" and dst_role in ("UNLABELED", "KNOWN_OTHER"):
        return "EXCHANGE_OUTFLOW"

    # Heuristic for newly rotated exchange deposit addresses:
    # Ripple sending with a DestinationTag to an unlabeled address is typically an institutional/exchange distribution
    if src_role == "RIPPLE" and dst_role == "UNLABELED" and has_dest_tag:
        return "EXCHANGE_INFLOW"

    return "WHALE_TRANSFER"


@dataclass
class BacktestMetrics:
    """Summary performance metrics for a backtest strategy variant."""

    strategy_name: str
    total_trades: int
    win_rate_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    sharpe_ratio: float
    final_equity: float


async def _fetch_entity_map(client: httpx.AsyncClient) -> dict[str, str]:
    """Fetch well-known and top-10k labeled addresses from XRPSCAN."""
    name_map: dict[str, str] = {}
    wk_task = asyncio.create_task(client.get(f"{XRPSCAN_BASE_URL}/names/well-known"))
    bal_task = asyncio.create_task(client.get(f"{XRPSCAN_BASE_URL}/balances"))

    for task in (wk_task, bal_task):
        try:
            resp = await task
            if resp.status_code == 200:
                data = resp.json()
                for row in data:
                    acct = row.get("account")
                    if not acct:
                        continue
                    if isinstance(row.get("name"), dict):
                        n = row["name"].get("name")
                    else:
                        n = row.get("name")
                    if n:
                        name_map[acct] = str(n)
        except Exception:
            pass
    return name_map


async def _fetch_sql_window(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    start_iso: str,
    end_iso: str,
    min_xrp: int = 1_000_000,
) -> list[list[Any]]:
    """Fetch all >=min_xrp Payment transactions within [start_iso, end_iso) via keyset pagination."""
    rows_all: list[list[Any]] = []
    cursor_end = end_iso

    async with sem:
        for _ in range(10):  # Up to 5,000 rows per 3-day slice if needed
            query = (
                "SELECT _date, Account, Destination, DestinationTag, "
                "meta.delivered_amount._value AS xrp, hash "
                'FROM "platform.xrpl.transactions" '
                "WHERE TransactionType = 'Payment' "
                "AND meta.TransactionResult = 'tesSUCCESS' "
                "AND meta.delivered_amount.currency = 'XRP' "
                f"AND meta.delivered_amount._value >= {min_xrp} "
                f"AND _date >= '{start_iso}' AND _date < '{cursor_end}' "
                "ORDER BY _date DESC"
            )
            try:
                resp = await client.post(
                    XRPSCAN_SQL_URL,
                    json={"format": "json", "query": query},
                )
                resp.raise_for_status()
                batch = resp.json().get("rows") or []
            except Exception:
                break

            if not batch:
                break
            rows_all.extend(batch)
            if len(batch) < 500:
                break
            # Advance keyset cursor to oldest timestamp in batch
            oldest_ts = batch[-1][0]
            if oldest_ts == cursor_end:
                break
            cursor_end = oldest_ts

    return rows_all


async def _fetch_ohlcv_90d(client: httpx.AsyncClient, days: int = 90) -> list[dict[str, Any]]:
    """Fetch 90 days of 1-Hour XRP/USDT candles from Binance.US."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = now_ms - (days * 24 * 3600 * 1000)
    bars: list[dict[str, Any]] = []

    cursor_ms = start_ms
    while cursor_ms < now_ms:
        try:
            resp = await client.get(
                BINANCE_KLINES_URL,
                params={
                    "symbol": "XRPUSDT",
                    "interval": "1h",
                    "startTime": cursor_ms,
                    "endTime": now_ms,
                    "limit": 1000,
                },
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception:
            break

        if not batch:
            break
        for k in batch:
            bars.append(
                {
                    "timestamp": datetime.fromtimestamp(k[0] / 1000.0, tz=timezone.utc).isoformat(),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
            )
        last_open_ms = int(batch[-1][0])
        if last_open_ms <= cursor_ms:
            break
        cursor_ms = last_open_ms + 3600 * 1000

    return bars


async def fetch_90d_dataset(
    days: int = 90,
    min_xrp: int = 1_000_000,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Fetch or load cached 90-day XRPL whale payments, entity map, and 1H XRP/USD bars."""
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_file = data_dir / f"whale_study_{days}d_{min_xrp}.json"

    if use_cache and cache_file.exists():
        age_sec = datetime.now().timestamp() - cache_file.stat().st_mtime
        if age_sec < 3600:
            return json.loads(cache_file.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    sem = asyncio.Semaphore(6)
    headers = {"User-Agent": "rippled-data-whale-study/2.0"}

    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
        entity_task = asyncio.create_task(_fetch_entity_map(client))
        ohlcv_task = asyncio.create_task(_fetch_ohlcv_90d(client, days=days))

        # Slice 90 days into 3-day windows so each slice is <500 rows (1 request per slice)
        step_days = 3
        window_tasks = []
        for offset in range(0, days, step_days):
            w_end = now - timedelta(days=offset)
            w_start = now - timedelta(days=min(days, offset + step_days))
            window_tasks.append(
                asyncio.create_task(
                    _fetch_sql_window(
                        client,
                        sem,
                        w_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        w_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        min_xrp=min_xrp,
                    )
                )
            )

        entity_map = await entity_task
        ohlcv_bars = await ohlcv_task
        window_results = await asyncio.gather(*window_tasks)

    seen_hashes: set[str] = set()
    tx_records: list[dict[str, Any]] = []
    for batch in window_results:
        for row in batch:
            dt_str, src, dst, tag, xrp_val, tx_hash = row[0], row[1], row[2], row[3], row[4], row[5]
            if tx_hash in seen_hashes:
                continue
            seen_hashes.add(tx_hash)
            src_ent = entity_map.get(src, "Unlabeled")
            dst_ent = entity_map.get(dst, "Unlabeled")
            src_role = classify_entity_role(src_ent)
            dst_role = classify_entity_role(dst_ent)
            flow_type = classify_whale_payment(src_role, dst_role, src_ent, dst_ent, tag is not None)
            tx_records.append(
                {
                    "timestamp": dt_str,
                    "account": src,
                    "source_entity": src_ent,
                    "source_role": src_role,
                    "destination": dst,
                    "dest_entity": dst_ent,
                    "dest_role": dst_role,
                    "destination_tag": tag,
                    "xrp": float(xrp_val or 0.0),
                    "flow_type": flow_type,
                    "hash": tx_hash,
                }
            )

    tx_records.sort(key=lambda x: x["timestamp"])
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "min_xrp": min_xrp,
        "transactions": tx_records,
        "ohlcv_1h": ohlcv_bars,
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _compute_strategy_metrics(
    name: str,
    equity_curve: list[float],
    trade_returns: list[float],
    initial_capital: float = 10_000.0,
) -> BacktestMetrics:
    """Compute standard quantitative backtest metrics from an equity curve and trade list."""
    final_eq = equity_curve[-1] if equity_curve else initial_capital
    tot_ret_pct = ((final_eq - initial_capital) / initial_capital) * 100.0

    # Max Drawdown
    peak = initial_capital
    max_dd_pct = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd_pct:
            max_dd_pct = dd

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    win_rate = (len(wins) / len(trade_returns) * 100.0) if trade_returns else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Hourly Sharpe Ratio (annualized by sqrt(24 * 365))
    if len(equity_curve) > 2:
        s_eq = pd.Series(equity_curve)
        rets = s_eq.pct_change().dropna()
        std = float(rets.std())
        sharpe = float((rets.mean() / std) * math.sqrt(24 * 365)) if std > 1e-12 else 0.0
    else:
        sharpe = 0.0

    return BacktestMetrics(
        strategy_name=name,
        total_trades=len(trade_returns),
        win_rate_pct=win_rate,
        total_return_pct=tot_ret_pct,
        max_drawdown_pct=max_dd_pct,
        profit_factor=pf,
        sharpe_ratio=sharpe,
        final_equity=final_eq,
    )


def run_90d_study_and_backtest(dataset: dict[str, Any]) -> dict[str, Any]:
    """Run the 90-day whale flow classification breakdown, event study, and A/B/C backtest."""
    txs = dataset.get("transactions") or []
    bars = dataset.get("ohlcv_1h") or []

    df_tx = pd.DataFrame(txs)
    df_bars = pd.DataFrame(bars)
    if df_bars.empty:
        raise ValueError("No OHLCV bars available for backtest.")

    df_bars["hour"] = pd.to_datetime(df_bars["timestamp"], utc=True).dt.floor("h")
    df_bars = df_bars.drop_duplicates(subset=["hour"]).sort_values("hour").reset_index(drop=True)

    # 1. Flow Breakdown Summary
    flow_summary: dict[str, dict[str, float]] = {}
    total_tx_count = len(df_tx)
    total_xrp_moved = float(df_tx["xrp"].sum()) if not df_tx.empty else 0.0

    if not df_tx.empty:
        df_tx["hour"] = pd.to_datetime(df_tx["timestamp"], utc=True).dt.floor("h")
        for ftype, grp in df_tx.groupby("flow_type"):
            cnt = int(len(grp))
            vol = float(grp["xrp"].sum())
            flow_summary[str(ftype)] = {
                "tx_count": cnt,
                "pct_of_txs": (cnt / total_tx_count * 100.0) if total_tx_count else 0.0,
                "total_xrp": vol,
                "pct_of_volume": (vol / total_xrp_moved * 100.0) if total_xrp_moved else 0.0,
            }

        # Aggregate hourly flows
        piv = (
            df_tx.pivot_table(
                index="hour",
                columns="flow_type",
                values="xrp",
                aggfunc="sum",
                fill_value=0.0,
            )
            .reset_index()
        )
        df_merged = pd.merge(df_bars, piv, on="hour", how="left")
    else:
        df_merged = df_bars.copy()

    for col in ("EXCHANGE_INFLOW", "EXCHANGE_OUTFLOW", "INTERNAL_NOISE", "WHALE_TRANSFER"):
        if col not in df_merged.columns:
            df_merged[col] = 0.0
        else:
            df_merged[col] = df_merged[col].fillna(0.0)

    # Net Flow = Outflow (withdrawals to cold storage) - Inflow (deposits to exchanges)
    df_merged["net_flow_1h"] = df_merged["EXCHANGE_OUTFLOW"] - df_merged["EXCHANGE_INFLOW"]
    df_merged["raw_whale_vol_1h"] = (
        df_merged["EXCHANGE_INFLOW"]
        + df_merged["EXCHANGE_OUTFLOW"]
        + df_merged["INTERNAL_NOISE"]
        + df_merged["WHALE_TRANSFER"]
    )

    # Rolling 24H Net Flow & Rolling 7-Day (168H) Z-Score
    df_merged["net_flow_24h"] = df_merged["net_flow_1h"].rolling(24, min_periods=1).sum()
    df_merged["inflow_24h"] = df_merged["EXCHANGE_INFLOW"].rolling(24, min_periods=1).sum()
    df_merged["outflow_24h"] = df_merged["EXCHANGE_OUTFLOW"].rolling(24, min_periods=1).sum()
    df_merged["raw_vol_24h"] = df_merged["raw_whale_vol_1h"].rolling(24, min_periods=1).sum()

    roll_mean = df_merged["net_flow_24h"].rolling(168, min_periods=24).mean()
    roll_std = df_merged["net_flow_24h"].rolling(168, min_periods=24).std().replace(0, float("nan"))
    df_merged["net_flow_z"] = ((df_merged["net_flow_24h"] - roll_mean) / roll_std).fillna(0.0)

    raw_mean = df_merged["raw_vol_24h"].rolling(168, min_periods=24).mean()
    raw_std = df_merged["raw_vol_24h"].rolling(168, min_periods=24).std().replace(0, float("nan"))
    df_merged["raw_vol_z"] = ((df_merged["raw_vol_24h"] - raw_mean) / raw_std).fillna(0.0)

    # Forward returns for Event Study (4H, 12H, 24H)
    for h in (4, 12, 24):
        df_merged[f"fwd_ret_{h}h"] = (df_merged["close"].shift(-h) / df_merged["close"] - 1.0) * 100.0

    # 2. Event Study Regimes
    regimes = {
        "Strong Net Outflow (Bullish Z > +1.5)": df_merged["net_flow_z"] > 1.5,
        "Moderate Net Outflow (+0.5 < Z <= +1.5)": (df_merged["net_flow_z"] > 0.5) & (df_merged["net_flow_z"] <= 1.5),
        "Neutral Flow (-0.5 <= Z <= +0.5)": (df_merged["net_flow_z"] >= -0.5) & (df_merged["net_flow_z"] <= 0.5),
        "Moderate Net Inflow (-1.5 <= Z < -0.5)": (df_merged["net_flow_z"] < -0.5) & (df_merged["net_flow_z"] >= -1.5),
        "Heavy Exchange Inflow (Bearish Z < -1.5)": df_merged["net_flow_z"] < -1.5,
        "Raw Unfiltered Whale Spike (Vol Z > +1.5)": df_merged["raw_vol_z"] > 1.5,
    }
    event_study: list[dict[str, Any]] = []
    valid_eval = df_merged.dropna(subset=["fwd_ret_24h"])
    for label, mask in regimes.items():
        sub = valid_eval[mask.reindex(valid_eval.index, fill_value=False)]
        cnt = int(len(sub))
        event_study.append(
            {
                "regime": label,
                "hours_observed": cnt,
                "avg_4h_ret_pct": float(sub["fwd_ret_4h"].mean()) if cnt else 0.0,
                "avg_12h_ret_pct": float(sub["fwd_ret_12h"].mean()) if cnt else 0.0,
                "avg_24h_ret_pct": float(sub["fwd_ret_24h"].mean()) if cnt else 0.0,
                "win_rate_24h_pct": float((sub["fwd_ret_24h"] > 0).mean() * 100.0) if cnt else 0.0,
            }
        )

    # 3. Strategy A/B/C Backtest Simulation on 1H XRP/USD
    # Technical indicators: 24H Donchian high breakout, 12H trailing low exit
    df_merged["high_24h"] = df_merged["high"].shift(1).rolling(24).max()
    df_merged["low_12h"] = df_merged["low"].shift(1).rolling(12).min()

    def simulate(mode: str) -> tuple[BacktestMetrics, list[float]]:
        initial_cap = 10_000.0
        equity = initial_cap
        in_pos = False
        entry_price = 0.0
        pos_mult = 1.0
        eq_curve: list[float] = []
        trade_rets: list[float] = []
        fee_rate = 0.001  # 10 bps per side

        for row in df_merged.itertuples():
            price = float(row.close)
            z = float(row.net_flow_z)
            h24 = row.high_24h
            l12 = row.low_12h

            if in_pos:
                # Check exit rules
                should_exit = False
                if mode in ("baseline", "flow_gated"):
                    if not math.isnan(l12) and price < l12:
                        should_exit = True
                    # In flow-gated mode, also exit early if extreme exchange dumping hits (Z < -2.0)
                    if mode == "flow_gated" and z < -2.0:
                        should_exit = True
                elif mode == "standalone_flow":
                    if z <= 0.0:
                        should_exit = True

                if should_exit:
                    raw_ret = (price - entry_price) / entry_price
                    net_ret = (raw_ret - 2 * fee_rate) * pos_mult
                    equity *= 1.0 + net_ret
                    trade_rets.append(net_ret * 100.0)
                    in_pos = False

            else:
                # Check entry rules
                if mode == "baseline":
                    if not math.isnan(h24) and price > h24:
                        in_pos = True
                        entry_price = price
                        pos_mult = 1.0
                elif mode == "flow_gated":
                    # Only take technical breakout if whales are NOT flooding exchanges (Z >= -0.75)
                    if not math.isnan(h24) and price > h24 and z >= -0.75:
                        in_pos = True
                        entry_price = price
                        pos_mult = 1.0
                elif mode == "standalone_flow":
                    # Buy purely when 24H Net Exchange Outflow Z-Score > +1.5 (ignoring price action)
                    if z > 1.5:
                        in_pos = True
                        entry_price = price
                        pos_mult = 1.0

            # Mark-to-market equity
            if in_pos:
                unrealized = ((price - entry_price) / entry_price - fee_rate) * pos_mult
                eq_curve.append(equity * (1.0 + unrealized))
            else:
                eq_curve.append(equity)

        label_map = {
            "baseline": "1. Baseline Technical Breakout (Price Only)",
            "flow_gated": "2. On-Chain Flow-Gated Breakout (Price + NetFlow Gate)",
            "standalone_flow": "3. Standalone Whale Flow Only (No Price Action)",
        }
        metrics = _compute_strategy_metrics(label_map[mode], eq_curve, trade_rets, initial_cap)
        return metrics, eq_curve

    m_base, eq_base = simulate("baseline")
    m_gated, eq_gated = simulate("flow_gated")
    m_flow, eq_flow = simulate("standalone_flow")

    # Buy & Hold benchmark
    first_close = float(df_merged["close"].iloc[0])
    bh_curve = [10_000.0 * (float(c) / first_close) for c in df_merged["close"]]
    bh_ret = ((bh_curve[-1] - 10_000.0) / 10_000.0) * 100.0

    df_merged["eq_baseline"] = eq_base
    df_merged["eq_flow_gated"] = eq_gated
    df_merged["eq_standalone_flow"] = eq_flow
    df_merged["eq_buy_hold"] = bh_curve

    recent_classified = sorted(txs, key=lambda x: x["timestamp"], reverse=True)[:100]

    return {
        "total_tx_count": total_tx_count,
        "total_xrp_moved": total_xrp_moved,
        "flow_summary": flow_summary,
        "event_study": event_study,
        "backtest_metrics": [asdict(m_base), asdict(m_gated), asdict(m_flow)],
        "buy_and_hold_return_pct": bh_ret,
        "recent_transactions": recent_classified,
        "timeseries": df_merged[
            [
                "hour",
                "close",
                "EXCHANGE_INFLOW",
                "EXCHANGE_OUTFLOW",
                "INTERNAL_NOISE",
                "net_flow_24h",
                "net_flow_z",
                "eq_baseline",
                "eq_flow_gated",
                "eq_standalone_flow",
                "eq_buy_hold",
            ]
        ].assign(hour=lambda d: d["hour"].astype(str)).to_dict(orient="records"),
    }


def format_study_report(results: dict[str, Any]) -> str:
    """Format the 90-day whale flow study and backtest results for CLI output."""
    lines: list[str] = []
    lines.append("==========================================================================================")
    lines.append("         90-DAY XRPL WHALE TRANSACTION STUDY & BACKTEST (>= 1,000,000 XRP PAYMENTS)       ")
    lines.append("==========================================================================================")
    lines.append(f"Total Whale Payments (>=1M XRP): {results['total_tx_count']:,}")
    lines.append(f"Total XRP Volume Analyzed:       {results['total_xrp_moved']:,.2f} XRP\n")

    lines.append("#### 1. On-Chain Whale Transaction Classification (90 Days) ####")
    lines.append(f"{'Flow Category':<25} {'Tx Count':>10} {'% Txs':>9} {'Total Volume (XRP)':>24} {'% Volume':>10}")
    lines.append("-" * 82)
    for ftype, stats in sorted(
        results["flow_summary"].items(), key=lambda kv: kv[1]["total_xrp"], reverse=True
    ):
        lines.append(
            f"{ftype:<25} {stats['tx_count']:>10,} {stats['pct_of_txs']:>8.2f}% "
            f"{stats['total_xrp']:>24,.2f} {stats['pct_of_volume']:>9.2f}%"
        )
    lines.append("")

    lines.append("#### 2. Event Study: Forward XRP/USD Returns by 24H Net Exchange Flow Regime ####")
    lines.append(
        f"{'24H Flow Regime':<44} {'Hours':>7} {'Avg 4H Ret':>12} "
        f"{'Avg 12H Ret':>12} {'Avg 24H Ret':>12} {'24H Win%':>10}"
    )
    lines.append("-" * 101)
    for row in results["event_study"]:
        lines.append(
            f"{row['regime']:<44} {row['hours_observed']:>7,} "
            f"{row['avg_4h_ret_pct']:>+11.2f}% {row['avg_12h_ret_pct']:>+11.2f}% "
            f"{row['avg_24h_ret_pct']:>+11.2f}% {row['win_rate_24h_pct']:>9.1f}%"
        )
    lines.append("")

    lines.append("#### 3. 90-Day Strategy Backtest Comparison ($10,000 Initial Capital, 1H Bars) ####")
    lines.append(
        f"{'Strategy Variant':<52} {'Trades':>6} {'Win%':>7} "
        f"{'Net Return':>11} {'Max DD':>9} {'Profit Fac':>10} {'Sharpe':>7} {'Final Equity':>14}"
    )
    lines.append("-" * 122)
    for m in results["backtest_metrics"]:
        lines.append(
            f"{m['strategy_name']:<52} {m['total_trades']:>6} {m['win_rate_pct']:>6.1f}% "
            f"{m['total_return_pct']:>+10.2f}% {m['max_drawdown_pct']:>8.2f}% "
            f"{m['profit_factor']:>10.2f} {m['sharpe_ratio']:>7.2f} ${m['final_equity']:>13,.2f}"
        )
    lines.append(f"{'Benchmark: 90-Day XRP/USD Buy & Hold':<52} {'-':>6} {'-':>7} {results['buy_and_hold_return_pct']:>+10.2f}%")
    return "\n".join(lines)


@click.command()
@click.option("--days", default=90, show_default=True, help="Historical lookback window in days.")
@click.option("--min-xrp", default=1_000_000, show_default=True, help="Minimum Payment size in XRP.")
@click.option("--refresh", is_flag=True, help="Force re-fetch from XRPSCAN SQL and Binance APIs.")
def main(days: int, min_xrp: int, refresh: bool) -> None:
    """Run the 90-day XRPL whale transaction flow study and strategy backtest."""
    dataset = asyncio.run(fetch_90d_dataset(days=days, min_xrp=min_xrp, use_cache=not refresh))
    results = run_90d_study_and_backtest(dataset)
    click.echo(format_study_report(results))


if __name__ == "__main__":
    main()
