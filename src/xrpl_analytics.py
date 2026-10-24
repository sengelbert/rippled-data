#!/usr/bin/env python3
"""XRPL Rich-List & Holdings Analytics.

Fetches XRP Ledger supply metrics, rich-list percentile brackets, balance tier
distributions, and top holder/entity analytics from public XRPL indexer APIs
(Rich-List.info, XRPSCAN, and public XRPL JSON-RPC) without requiring a local
rippled node.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import click
import httpx

DROPS_PER_XRP = 1_000_000
MAX_XRP_SUPPLY = 100_000_000_000.0

RICHLIST_BASE_URL = "https://rich-list.info/api"
XRPSCAN_BASE_URL = "https://api.xrpscan.com/api/v1"
XRPL_RPC_URL = "https://xrplcluster.com/"


def drops_to_xrp(drops: int | float | str | None) -> float:
    """Convert drops (10^-6 XRP) to XRP."""
    if drops is None:
        return 0.0
    return float(drops) / DROPS_PER_XRP


@dataclass
class SupplySummary:
    """Global XRP Ledger supply and account summary."""

    ledger_index: int
    close_time: str
    total_accounts: int
    max_supply_xrp: float
    total_xrp: float
    burned_xrp: float
    wallet_xrp: float
    escrow_xrp: float
    average_balance_xrp: float


@dataclass
class PercentileBracket:
    """Rich-list percentile bracket (e.g., Top 0.01% / 100% - 99.99%)."""

    top_percentile_label: str
    rank_max_pct: float
    rank_min_pct: float
    cumulative_accounts: int
    bracket_accounts: int
    total_accounts: int
    max_balance_xrp: float
    min_balance_xrp: float


@dataclass
class BalanceRangeTier:
    """Account count and total XRP held within a specific balance range."""

    balance_range: str
    account_count: int
    pct_of_accounts: float
    total_xrp: float
    pct_of_wallet_xrp: float


@dataclass
class AccountHolding:
    """Top XRP holder record with liquid, escrow, and entity attribution."""

    rank: int
    account: str
    entity_name: str
    entity_desc: str
    domain: str
    liquid_xrp: float
    escrow_xrp: float
    total_xrp: float
    pct_of_total_supply: float


@dataclass
class EntitySummary:
    """Aggregated holdings across all labeled wallets for a single entity."""

    entity_name: str
    domain: str
    wallet_count: int
    liquid_xrp: float
    escrow_xrp: float
    total_xrp: float
    pct_of_total_supply: float


@dataclass
class AnalyticsSnapshot:
    """Complete XRPL rich-list and holdings analytics snapshot."""

    fetched_at: str
    supply: SupplySummary
    percentile_brackets: list[PercentileBracket] = field(default_factory=list)
    top10k_supply_brackets: list[dict[str, Any]] = field(default_factory=list)
    balance_ranges: list[BalanceRangeTier] = field(default_factory=list)
    top_accounts_by_total: list[AccountHolding] = field(default_factory=list)
    top_accounts_by_liquid: list[AccountHolding] = field(default_factory=list)
    top_entities: list[EntitySummary] = field(default_factory=list)
    looked_up_account: dict[str, Any] | None = None


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    """Perform an async GET request and return parsed JSON or None on failure."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def _post_rpc(client: httpx.AsyncClient, method: str, params: dict[str, Any]) -> Any:
    """Perform an async JSON-RPC call to a public XRPL node."""
    try:
        resp = await client.post(
            XRPL_RPC_URL,
            json={"method": method, "params": [params]},
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception:
        return None


async def fetch_raw_data(account_lookup: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Concurrently fetch XRPL rich-list, balances, and supply metrics."""
    headers = {"User-Agent": "rippled-data-analytics/2.0"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        tasks: dict[str, asyncio.Task[Any]] = {
            "rl_stats": asyncio.create_task(_get_json(client, f"{RICHLIST_BASE_URL}/stats")),
            "rl_percentiles": asyncio.create_task(
                _get_json(client, f"{RICHLIST_BASE_URL}/stats/percentiles")
            ),
            "rl_ranges": asyncio.create_task(
                _get_json(client, f"{RICHLIST_BASE_URL}/stats/balance-ranges")
            ),
            "rl_top": asyncio.create_task(
                _get_json(client, f"{RICHLIST_BASE_URL}/richlist?limit=25&offset=0")
            ),
            "xrpscan_balances": asyncio.create_task(
                _get_json(client, f"{XRPSCAN_BASE_URL}/balances")
            ),
            "xrpscan_xrp_fact": asyncio.create_task(
                _get_json(client, f"{XRPSCAN_BASE_URL}/fact/XRP")
            ),
            "xrpscan_obj_count": asyncio.create_task(
                _get_json(client, f"{XRPSCAN_BASE_URL}/fact/ObjectCount")
            ),
            "xrpl_ledger": asyncio.create_task(
                _post_rpc(client, "ledger", {"ledger_index": "validated"})
            ),
        }
        if account_lookup:
            tasks["rl_account"] = asyncio.create_task(
                _get_json(client, f"{RICHLIST_BASE_URL}/search?account={account_lookup}")
            )
            tasks["xrpscan_account"] = asyncio.create_task(
                _get_json(client, f"{XRPSCAN_BASE_URL}/account/{account_lookup}")
            )

        results = {}
        for key, task in tasks.items():
            results[key] = await task
        return results


async def fetch_wallet_raw(account: str, timeout: float = 15.0) -> dict[str, Any]:
    """Fetch only the wallet-specific endpoints for fast interactive lookups."""
    headers = {"User-Agent": "rippled-data-analytics/2.0"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        rl_task = asyncio.create_task(
            _get_json(client, f"{RICHLIST_BASE_URL}/search?account={account}")
        )
        xs_task = asyncio.create_task(
            _get_json(client, f"{XRPSCAN_BASE_URL}/account/{account}")
        )
        return {
            "rl_account": await rl_task,
            "xrpscan_account": await xs_task,
        }


def build_analytics(raw: dict[str, Any], top_n: int = 15) -> AnalyticsSnapshot:
    """Transform raw API payloads into a structured AnalyticsSnapshot."""
    rl_stats = (raw.get("rl_stats") or {}).get("data") or {}
    xrp_fact = raw.get("xrpscan_xrp_fact") or {}
    obj_count = raw.get("xrpscan_obj_count") or {}
    xrpl_ledger = (raw.get("xrpl_ledger") or {}).get("ledger") or {}
    xrpscan_balances: list[dict[str, Any]] = raw.get("xrpscan_balances") or []
    rl_top_data: list[dict[str, Any]] = (raw.get("rl_top") or {}).get("data") or []

    # 1. Supply Summary
    ledger_index = int(
        rl_stats.get("ledger_index")
        or xrpl_ledger.get("ledger_index")
        or 0
    )
    close_time = (
        rl_stats.get("ledger_date")
        or xrpl_ledger.get("close_time_iso")
        or xrpl_ledger.get("close_time_human")
        or datetime.now(timezone.utc).isoformat()
    )
    total_accounts = int(
        rl_stats.get("accounts")
        or obj_count.get("AccountRoot")
        or len(xrpscan_balances)
        or 1
    )

    total_xrp = float(
        rl_stats.get("total_xrp")
        or drops_to_xrp(xrp_fact.get("total_coins") or xrpl_ledger.get("total_coins"))
    )
    wallet_xrp = float(
        rl_stats.get("wallet_xrp")
        or drops_to_xrp(xrp_fact.get("circulating_coins"))
    )
    escrow_xrp = float(
        rl_stats.get("escrow_xrp")
        or drops_to_xrp(xrp_fact.get("escrowed_coins"))
    )
    burned_xrp = (
        drops_to_xrp(xrp_fact.get("burned_coins"))
        if xrp_fact.get("burned_coins")
        else max(0.0, MAX_XRP_SUPPLY - total_xrp)
    )
    avg_balance_xrp = float(
        rl_stats.get("average_balance_xrp")
        or (wallet_xrp / total_accounts if total_accounts else 0.0)
    )

    supply = SupplySummary(
        ledger_index=ledger_index,
        close_time=close_time,
        total_accounts=total_accounts,
        max_supply_xrp=MAX_XRP_SUPPLY,
        total_xrp=total_xrp,
        burned_xrp=burned_xrp,
        wallet_xrp=wallet_xrp,
        escrow_xrp=escrow_xrp,
        average_balance_xrp=avg_balance_xrp,
    )

    # Determine #1 liquid account balance
    max_liquid_xrp = 0.0
    if rl_top_data:
        max_liquid_xrp = float(rl_top_data[0].get("balance_xrp", 0.0))
    elif xrpscan_balances:
        max_liquid_xrp = max(drops_to_xrp(b.get("balance", 0)) for b in xrpscan_balances)

    # 2. Rich-List Percentile Brackets (100% - 99.99% down to 95% - 90%)
    rl_percentiles: list[dict[str, Any]] = (raw.get("rl_percentiles") or {}).get("data") or []
    percentile_brackets: list[PercentileBracket] = []

    if rl_percentiles:
        prev_pct_top = 0.0
        prev_cum_accounts = 0
        prev_threshold_xrp = max_liquid_xrp

        for row in rl_percentiles:
            raw_label = str(row.get("percentile", "0 %")).replace("%", "").strip()
            pct_val = float(raw_label)
            cum_accounts = int(row.get("account_count", 0))
            threshold_xrp = float(row.get("balance_threshold_xrp", 0.0))

            rank_max_pct = round(100.0 - prev_pct_top, 4)
            rank_min_pct = round(100.0 - pct_val, 4)
            bracket_accounts = max(0, cum_accounts - prev_cum_accounts)
            upper_xrp = prev_threshold_xrp if prev_threshold_xrp > 0 else threshold_xrp

            percentile_brackets.append(
                PercentileBracket(
                    top_percentile_label=f"Top {raw_label}%",
                    rank_max_pct=rank_max_pct,
                    rank_min_pct=rank_min_pct,
                    cumulative_accounts=cum_accounts,
                    bracket_accounts=bracket_accounts,
                    total_accounts=total_accounts,
                    max_balance_xrp=upper_xrp,
                    min_balance_xrp=threshold_xrp,
                )
            )
            prev_pct_top = pct_val
            prev_cum_accounts = cum_accounts
            prev_threshold_xrp = threshold_xrp
    elif xrpscan_balances:
        # Fallback using XRPSCAN top 10,000 balances
        sorted_liquid = sorted(
            (drops_to_xrp(b.get("balance", 0)) for b in xrpscan_balances),
            reverse=True,
        )
        for pct_val, prev_pct in [(0.01, 0.0), (0.1, 0.01)]:
            cum_idx = min(len(sorted_liquid), max(1, int(round(total_accounts * (pct_val / 100.0)))))
            prev_idx = int(round(total_accounts * (prev_pct / 100.0)))
            percentile_brackets.append(
                PercentileBracket(
                    top_percentile_label=f"Top {pct_val}%",
                    rank_max_pct=round(100.0 - prev_pct, 4),
                    rank_min_pct=round(100.0 - pct_val, 4),
                    cumulative_accounts=cum_idx,
                    bracket_accounts=max(0, cum_idx - prev_idx),
                    total_accounts=total_accounts,
                    max_balance_xrp=sorted_liquid[prev_idx] if prev_idx < len(sorted_liquid) else 0.0,
                    min_balance_xrp=sorted_liquid[cum_idx - 1],
                )
            )

    # 3. Balance Range Tiers
    rl_ranges: list[dict[str, Any]] = (raw.get("rl_ranges") or {}).get("data") or []
    balance_ranges: list[BalanceRangeTier] = []
    for item in rl_ranges:
        acct_cnt = int(item.get("account_count", 0))
        tier_xrp = float(item.get("total_xrp", 0.0))
        balance_ranges.append(
            BalanceRangeTier(
                balance_range=str(item.get("balance_range", "")),
                account_count=acct_cnt,
                pct_of_accounts=(acct_cnt / total_accounts * 100.0) if total_accounts else 0.0,
                total_xrp=tier_xrp,
                pct_of_wallet_xrp=(tier_xrp / wallet_xrp * 100.0) if wallet_xrp else 0.0,
            )
        )

    # 4. Top Accounts & Entity Aggregation (from XRPSCAN Top 10,000)
    all_holdings: list[AccountHolding] = []
    entity_agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"domain": "", "wallet_count": 0, "liquid_xrp": 0.0, "escrow_xrp": 0.0, "total_xrp": 0.0}
    )

    for idx, entry in enumerate(xrpscan_balances, start=1):
        acct = str(entry.get("account", ""))
        liquid = drops_to_xrp(entry.get("balance", 0))
        escrow = drops_to_xrp(entry.get("escrow", 0))
        total_held = drops_to_xrp(entry.get("supply", 0)) or (liquid + escrow)

        name_obj = entry.get("name") or {}
        entity_name = str(name_obj.get("name") or "Unlabeled")
        entity_desc = str(name_obj.get("desc") or "")
        domain = str(name_obj.get("domain") or "")

        pct_supply = (total_held / total_xrp * 100.0) if total_xrp else 0.0
        holding = AccountHolding(
            rank=idx,
            account=acct,
            entity_name=entity_name,
            entity_desc=entity_desc,
            domain=domain,
            liquid_xrp=liquid,
            escrow_xrp=escrow,
            total_xrp=total_held,
            pct_of_total_supply=pct_supply,
        )
        all_holdings.append(holding)

        if entity_name != "Unlabeled":
            agg = entity_agg[entity_name]
            if domain and not agg["domain"]:
                agg["domain"] = domain
            agg["wallet_count"] += 1
            agg["liquid_xrp"] += liquid
            agg["escrow_xrp"] += escrow
            agg["total_xrp"] += total_held

    top_by_total = sorted(all_holdings, key=lambda h: h.total_xrp, reverse=True)[:top_n]
    for rank_idx, item in enumerate(top_by_total, start=1):
        item.rank = rank_idx

    top_by_liquid_sorted = sorted(all_holdings, key=lambda h: h.liquid_xrp, reverse=True)[:top_n]
    top_by_liquid = [
        AccountHolding(
            rank=rank_idx,
            account=h.account,
            entity_name=h.entity_name,
            entity_desc=h.entity_desc,
            domain=h.domain,
            liquid_xrp=h.liquid_xrp,
            escrow_xrp=h.escrow_xrp,
            total_xrp=h.total_xrp,
            pct_of_total_supply=(h.liquid_xrp / wallet_xrp * 100.0) if wallet_xrp else 0.0,
        )
        for rank_idx, h in enumerate(top_by_liquid_sorted, start=1)
    ]

    top_entities = [
        EntitySummary(
            entity_name=ename,
            domain=vals["domain"],
            wallet_count=vals["wallet_count"],
            liquid_xrp=vals["liquid_xrp"],
            escrow_xrp=vals["escrow_xrp"],
            total_xrp=vals["total_xrp"],
            pct_of_total_supply=(vals["total_xrp"] / total_xrp * 100.0) if total_xrp else 0.0,
        )
        for ename, vals in entity_agg.items()
    ]
    top_entities.sort(key=lambda e: e.total_xrp, reverse=True)
    top_entities = top_entities[:top_n]

    # 5. Top 10,000 Supply Concentration Brackets (Top 10, 50, 100, 500, 1000, 5000, 10000)
    top10k_supply_brackets: list[dict[str, Any]] = []
    if all_holdings:
        sorted_total = sorted(all_holdings, key=lambda h: h.total_xrp, reverse=True)
        for count in [10, 50, 100, 500, 1_000, 5_000, 10_000]:
            if count <= len(sorted_total):
                tot_slice = sorted_total[:count]
                sum_tot = sum(h.total_xrp for h in tot_slice)
                sum_liq = sum(h.liquid_xrp for h in tot_slice)
                top10k_supply_brackets.append(
                    {
                        "top_accounts": count,
                        "pct_of_all_accounts": (count / total_accounts * 100.0)
                        if total_accounts
                        else 0.0,
                        "total_xrp_held": sum_tot,
                        "pct_of_total_supply": (sum_tot / total_xrp * 100.0) if total_xrp else 0.0,
                        "min_total_xrp": tot_slice[-1].total_xrp,
                        "liquid_xrp_held": sum_liq,
                        "pct_of_liquid_supply": (sum_liq / wallet_xrp * 100.0)
                        if wallet_xrp
                        else 0.0,
                    }
                )

    # 6. Optional Account Lookup
    looked_up_account = None
    rl_acct = (raw.get("rl_account") or {}).get("data")
    xs_acct = raw.get("xrpscan_account")
    if rl_acct or xs_acct:
        acct_id = (rl_acct or {}).get("account_id") or (xs_acct or {}).get("account") or (xs_acct or {}).get("Account")
        liq_bal = (
            float(rl_acct["balance_xrp"])
            if rl_acct and "balance_xrp" in rl_acct
            else float((xs_acct or {}).get("xrpBalance") or drops_to_xrp((xs_acct or {}).get("Balance")) or 0.0)
        )
        escrows_raw = (rl_acct or {}).get("escrows") or []
        escrows_list = [
            {
                "amount_xrp": drops_to_xrp(e.get("amount", 0)),
                "destination": e.get("destination") or acct_id,
                "finish_after": e.get("finish_after"),
            }
            for e in escrows_raw
        ]
        escrow_bal = sum(e["amount_xrp"] for e in escrows_list)
        total_bal = liq_bal + escrow_bal

        rank = int(rl_acct["rank"]) if rl_acct and rl_acct.get("rank") else None
        top_pct = (rank / total_accounts * 100.0) if (rank and total_accounts) else None
        wealth_percentile = (100.0 - top_pct) if top_pct is not None else None

        # Determine current percentile bracket and next bracket target
        current_bracket = "Outside Top 10%"
        next_bracket_label = None
        next_bracket_threshold_xrp = None
        xrp_to_next_bracket = None

        if percentile_brackets:
            # Ordered from Top 0.01% (index 0) to Top 10% (index -1)
            matched_idx = None
            for idx, b in enumerate(percentile_brackets):
                if liq_bal >= b.min_balance_xrp:
                    matched_idx = idx
                    break
            if matched_idx is not None:
                current_bracket = percentile_brackets[matched_idx].top_percentile_label
                if matched_idx > 0:
                    prev_b = percentile_brackets[matched_idx - 1]
                    next_bracket_label = prev_b.top_percentile_label
                    next_bracket_threshold_xrp = prev_b.min_balance_xrp
                    xrp_to_next_bracket = max(0.0, prev_b.min_balance_xrp - liq_bal)
            else:
                lowest_b = percentile_brackets[-1]
                next_bracket_label = lowest_b.top_percentile_label
                next_bracket_threshold_xrp = lowest_b.min_balance_xrp
                xrp_to_next_bracket = max(0.0, lowest_b.min_balance_xrp - liq_bal)

        acct_name_obj = (xs_acct or {}).get("accountName") or {}
        parent_name_obj = (xs_acct or {}).get("parentName") or {}
        entity_name = acct_name_obj.get("name") or "Unlabeled"
        if acct_name_obj.get("desc"):
            entity_name = f"{entity_name} ({acct_name_obj['desc']})"

        looked_up_account = {
            "account": acct_id,
            "entity_name": entity_name,
            "domain": acct_name_obj.get("domain") or "",
            "twitter": acct_name_obj.get("twitter") or "",
            "liquid_xrp": liq_bal,
            "escrow_xrp": escrow_bal,
            "total_xrp": total_bal,
            "pct_of_total_supply": (total_bal / total_xrp * 100.0) if total_xrp else 0.0,
            "pct_of_liquid_supply": (liq_bal / wallet_xrp * 100.0) if wallet_xrp else 0.0,
            "rank": rank,
            "total_accounts": total_accounts,
            "top_percentile": top_pct,
            "wealth_percentile": wealth_percentile,
            "current_bracket": current_bracket,
            "next_bracket_label": next_bracket_label,
            "next_bracket_threshold_xrp": next_bracket_threshold_xrp,
            "xrp_to_next_bracket": xrp_to_next_bracket,
            "inception": (xs_acct or {}).get("inception"),
            "initial_balance": (xs_acct or {}).get("initial_balance"),
            "parent": (xs_acct or {}).get("parent"),
            "parent_entity": parent_name_obj.get("name") if parent_name_obj else None,
            "owner_count": (xs_acct or {}).get("ownerCount") or (xs_acct or {}).get("OwnerCount") or 0,
            "sequence": (xs_acct or {}).get("sequence") or (xs_acct or {}).get("Sequence") or 0,
            "escrows": escrows_list,
        }

    return AnalyticsSnapshot(
        fetched_at=datetime.now(timezone.utc).isoformat(),
        supply=supply,
        percentile_brackets=percentile_brackets,
        top10k_supply_brackets=top10k_supply_brackets,
        balance_ranges=balance_ranges,
        top_accounts_by_total=top_by_total,
        top_accounts_by_liquid=top_by_liquid,
        top_entities=top_entities,
        looked_up_account=looked_up_account,
    )


def format_report(snapshot: AnalyticsSnapshot) -> str:
    """Format an AnalyticsSnapshot into a human-readable CLI report."""
    s = snapshot.supply
    lines: list[str] = []

    wallet_pct = (s.wallet_xrp / s.total_xrp * 100.0) if s.total_xrp else 0.0
    escrow_pct = (s.escrow_xrp / s.total_xrp * 100.0) if s.total_xrp else 0.0

    lines.append("#### Ledger & Supply Data ####")
    lines.append(f"Ledger Index:       {s.ledger_index:,}")
    lines.append(f"Close Time:         {s.close_time}")
    lines.append(f"Total Accounts:     {s.total_accounts:,}")
    lines.append(f"Max Supply:         {s.max_supply_xrp:,.2f} XRP")
    lines.append(f"Total Remaining:    {s.total_xrp:,.2f} XRP (Burned: {s.burned_xrp:,.2f} XRP)")
    lines.append(f"Liquid in Wallets:  {s.wallet_xrp:,.2f} XRP ({wallet_pct:.2f}%)")
    lines.append(f"Locked in Escrow:   {s.escrow_xrp:,.2f} XRP ({escrow_pct:.2f}%)")
    lines.append(f"Average Balance:    {s.average_balance_xrp:,.2f} XRP / account")
    lines.append("")

    if snapshot.looked_up_account:
        la = snapshot.looked_up_account
        lines.append("#### Account Lookup ####")
        label = f" ({la['entity_name']})" if la.get("entity_name") != "Unlabeled" else ""
        lines.append(f"Account:            {la['account']}{label}")
        lines.append(f"Liquid Balance:     {la['liquid_xrp']:,.6f} XRP")
        if la.get("escrow_xrp", 0) > 0:
            lines.append(f"Escrowed Balance:   {la['escrow_xrp']:,.2f} XRP ({len(la.get('escrows', []))} escrows)")
            lines.append(f"Total Holdings:     {la['total_xrp']:,.2f} XRP ({la['pct_of_total_supply']:.4f}% of supply)")
        if la.get("rank"):
            lines.append(
                f"Global Rank:        #{la['rank']:,} out of {la['total_accounts']:,} "
                f"(Top {la['top_percentile']:.4f}% | {la['wealth_percentile']:.4f}th Wealth Percentile)"
            )
            lines.append(f"Rich-List Tier:     {la.get('current_bracket', '-')}")
            if la.get("next_bracket_label"):
                lines.append(
                    f"Next Tier Target:   {la['next_bracket_label']} "
                    f"(Requires {la['next_bracket_threshold_xrp']:,.2f} XRP | "
                    f"+{la['xrp_to_next_bracket']:,.2f} XRP needed)"
                )
        lines.append("")

    if snapshot.percentile_brackets:
        lines.append("#### Account Percentile Brackets (Rich List) ####")
        for b in snapshot.percentile_brackets:
            lines.append(
                f"Top {b.rank_max_pct:g}% - {b.rank_min_pct:g}% ({b.top_percentile_label:<9}): "
                f"Total Accounts: {b.cumulative_accounts:>7,} out of {b.total_accounts:,} "
                f"({b.bracket_accounts:>7,} inclusive) | "
                f"Balance Range: {b.max_balance_xrp:>16,.2f} - {b.min_balance_xrp:>12,.2f} XRP"
            )
        lines.append("")

    if snapshot.top10k_supply_brackets:
        lines.append("#### Top Whale Supply Concentration (Top 10,000 Indexed by Total Holdings) ####")
        lines.append(
            f"{'Tier':<12} {'% Accts':>9} | {'Total Held (Liquid+Escrow)':>28} {'% Supply':>9} "
            f"{'Min Total (XRP)':>18} | {'Liquid Component':>20} {'% Wallet XRP':>13}"
        )
        lines.append("-" * 119)
        for row in snapshot.top10k_supply_brackets:
            tier_lbl = f"Top {row['top_accounts']:,}"
            lines.append(
                f"{tier_lbl:<12} {row['pct_of_all_accounts']:>8.4f}% | "
                f"{row['total_xrp_held']:>24,.2f} XRP {row['pct_of_total_supply']:>8.2f}% "
                f"{row['min_total_xrp']:>18,.2f} | "
                f"{row['liquid_xrp_held']:>16,.2f} XRP {row['pct_of_liquid_supply']:>12.2f}%"
            )
        lines.append("")

    if snapshot.balance_ranges:
        lines.append("#### Balance Distribution by Range (Liquid XRP) ####")
        lines.append(
            f"{'Balance Range (XRP)':<30} {'# Accounts':>12} {'% Accounts':>11} "
            f"{'Total XRP in Tier':>22} {'% Wallet XRP':>13}"
        )
        lines.append("-" * 92)
        for r in snapshot.balance_ranges:
            lines.append(
                f"{r.balance_range:<30} {r.account_count:>12,} {r.pct_of_accounts:>10.4f}% "
                f"{r.total_xrp:>22,.2f} {r.pct_of_wallet_xrp:>12.2f}%"
            )
        lines.append("")

    if snapshot.top_entities:
        lines.append(f"#### Top {len(snapshot.top_entities)} Known Entities by Total Holdings (Top 10k Wallets) ####")
        lines.append(
            f"{'Rank':<5} {'Entity':<20} {'Wallets':>7} {'Liquid XRP':>20} "
            f"{'Escrowed XRP':>20} {'Total XRP':>20} {'% Supply':>9}"
        )
        lines.append("-" * 107)
        for idx, ent in enumerate(snapshot.top_entities, start=1):
            lines.append(
                f"{idx:<5} {ent.entity_name[:20]:<20} {ent.wallet_count:>7,} "
                f"{ent.liquid_xrp:>20,.2f} {ent.escrow_xrp:>20,.2f} "
                f"{ent.total_xrp:>20,.2f} {ent.pct_of_total_supply:>8.2f}%"
            )
        lines.append("")

    if snapshot.top_accounts_by_total:
        lines.append(f"#### Top {len(snapshot.top_accounts_by_total)} Accounts by Total Holdings (Liquid + Escrow) ####")
        lines.append(
            f"{'Rank':<5} {'Account':<36} {'Entity':<18} {'Liquid XRP':>18} "
            f"{'Escrow XRP':>18} {'Total XRP':>18} {'% Supply':>9}"
        )
        lines.append("-" * 128)
        for h in snapshot.top_accounts_by_total:
            entity_lbl = h.entity_name if h.entity_name != "Unlabeled" else "-"
            if h.entity_desc and entity_lbl != "-":
                entity_lbl = f"{entity_lbl} ({h.entity_desc})"
            lines.append(
                f"{h.rank:<5} {h.account:<36} {entity_lbl[:18]:<18} "
                f"{h.liquid_xrp:>18,.2f} {h.escrow_xrp:>18,.2f} "
                f"{h.total_xrp:>18,.2f} {h.pct_of_total_supply:>8.2f}%"
            )
        lines.append("")

    if snapshot.top_accounts_by_liquid:
        lines.append(f"#### Top {len(snapshot.top_accounts_by_liquid)} Accounts by Liquid Balance ####")
        lines.append(
            f"{'Rank':<5} {'Account':<36} {'Entity':<18} {'Liquid XRP':>18} "
            f"{'Escrow XRP':>18} {'% Wallet XRP':>13}"
        )
        lines.append("-" * 114)
        for h in snapshot.top_accounts_by_liquid:
            entity_lbl = h.entity_name if h.entity_name != "Unlabeled" else "-"
            if h.entity_desc and entity_lbl != "-":
                entity_lbl = f"{entity_lbl} ({h.entity_desc})"
            lines.append(
                f"{h.rank:<5} {h.account:<36} {entity_lbl[:18]:<18} "
                f"{h.liquid_xrp:>18,.2f} {h.escrow_xrp:>18,.2f} "
                f"{h.pct_of_total_supply:>12.2f}%"
            )

    return "\n".join(lines)


@click.command()
@click.option("-t", "--top", default=15, show_default=True, help="Number of top accounts and entities to display.")
@click.option("-a", "--account", default=None, help="Look up rank and balance details for a specific XRPL address.")
@click.option("-s", "--save", is_flag=True, help="Save raw API snapshot to data/<ledger_index>_snapshot.json.")
@click.option("-f", "--from-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None, help="Load raw snapshot from a local JSON file instead of querying APIs.")
@click.option("--json-output", is_flag=True, help="Output structured analytics as JSON.")
def main(top: int, account: str | None, save: bool, from_file: Path | None, json_output: bool) -> None:
    """Fetch and analyze XRP Ledger Rich-List, holdings distribution, and top entities."""
    if from_file:
        raw_data = json.loads(from_file.read_text(encoding="utf-8"))
    else:
        raw_data = asyncio.run(fetch_raw_data(account_lookup=account))

    snapshot = build_analytics(raw_data, top_n=top)

    if save and not from_file:
        repo_root = Path(__file__).resolve().parent.parent
        data_dir = repo_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        out_path = data_dir / f"ledger_{snapshot.supply.ledger_index}_snapshot.json"
        out_path.write_text(json.dumps(raw_data, indent=2), encoding="utf-8")
        if not json_output:
            click.echo(f"Saved snapshot to {out_path}\n", err=True)

    if json_output:
        click.echo(json.dumps(asdict(snapshot), indent=2))
    else:
        click.echo(format_report(snapshot))


if __name__ == "__main__":
    main()
