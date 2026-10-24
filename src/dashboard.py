from __future__ import annotations

import asyncio
from datetime import datetime
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xrpl_analytics import (
    AnalyticsSnapshot,
    build_analytics,
    fetch_raw_data,
    fetch_wallet_raw,
)

st.set_page_config(
    page_title="XRPL Rich-List & Holdings Dashboard",
    page_icon="💎",
    layout="wide",
)


@st.cache_data(ttl=300, show_spinner=False)
def load_global_raw_data() -> dict:
    """Fetch and cache global XRPL rich-list, supply, and top-10k data for 5 minutes."""
    return asyncio.run(fetch_raw_data(account_lookup=None))


@st.cache_data(ttl=60, show_spinner=False)
def load_wallet_lookup(address: str) -> dict:
    """Fetch and cache individual XRPL wallet lookup for 60 seconds."""
    return asyncio.run(fetch_wallet_raw(account=address.strip()))


def determine_balance_tier(balance_xrp: float) -> str:
    """Return the human-readable balance range tier for a given liquid XRP balance."""
    thresholds = [
        (1_000_000_000, "1,000,000,000 - Infinity"),
        (500_000_000, "500,000,000 - 1,000,000,000"),
        (100_000_000, "100,000,000 - 500,000,000"),
        (20_000_000, "20,000,000 - 100,000,000"),
        (10_000_000, "10,000,000 - 20,000,000"),
        (5_000_000, "5,000,000 - 10,000,000"),
        (1_000_000, "1,000,000 - 5,000,000"),
        (500_000, "500,000 - 1,000,000"),
        (100_000, "100,000 - 500,000"),
        (75_000, "75,000 - 100,000"),
        (50_000, "50,000 - 75,000"),
        (25_000, "25,000 - 50,000"),
        (10_000, "10,000 - 25,000"),
        (5_000, "5,000 - 10,000"),
        (1_000, "1,000 - 5,000"),
        (500, "500 - 1,000"),
        (20, "20 - 500"),
        (0, "0 - 20"),
    ]
    for min_val, label in thresholds:
        if balance_xrp >= min_val:
            return label
    return "0 - 20"


# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Dashboard Controls")
    top_n = st.slider("Top Accounts / Entities to Show", min_value=10, max_value=100, value=25, step=5)
    if st.button("🔄 Refresh Ledger Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.subheader("🧪 Sample Wallets")
    st.caption("Click to populate the wallet search:")
    sample_wallets = {
        "🥇 #1 Liquid (Bithumb)": "rPyCQm8E5j78PDbrfKF24fRC7qUAk1kDMZ",
        "🔒 #1 Escrow (Ripple 11)": "rB3WNZc45gxzW31zxfXdkx8HusAhoqscPn",
        "🏦 Binance Cold Wallet": "rs8ZPbYqgecRcDzQpJYAMhSxSi5htsjnza",
        "🪶 Retail Wallet (~11 XRP)": "rEy8TFcrAPvhpKrwyrscNYyqBGUkE9hKaJ",
    }
    for label, addr in sample_wallets.items():
        if st.button(label, key=f"sample_{addr}", use_container_width=True):
            st.session_state["wallet_input"] = addr

# --- Load Global Data ---
with st.spinner("Fetching live XRPL Rich-List & supply telemetry..."):
    raw_global = load_global_raw_data()

# --- Header ---
st.title("💎 XRPL Rich-List & Holdings Analytics")

# --- Wallet Search Section ---
st.subheader("🔍 Wallet Wealth Percentile & Rank Lookup")
search_col1, search_col2 = st.columns([4, 1])
with search_col1:
    wallet_query = st.text_input(
        "Enter an XRP Ledger Address (r...)",
        key="wallet_input",
        placeholder="e.g., rPyCQm8E5j78PDbrfKF24fRC7qUAk1kDMZ",
        label_visibility="collapsed",
    )
with search_col2:
    clear_clicked = st.button("✖ Clear Search", use_container_width=True)
    if clear_clicked and st.session_state.get("wallet_input"):
        st.session_state["wallet_input"] = ""
        st.rerun()

combined_raw = dict(raw_global)
if wallet_query and wallet_query.strip():
    with st.spinner(f"Looking up {wallet_query.strip()}..."):
        wallet_raw = load_wallet_lookup(wallet_query.strip())
        combined_raw.update(wallet_raw)

snapshot: AnalyticsSnapshot = build_analytics(combined_raw, top_n=top_n)
s = snapshot.supply

# --- Display Wallet Search Results if Active ---
if wallet_query and wallet_query.strip():
    la = snapshot.looked_up_account
    if not la or (la.get("rank") is None and la.get("liquid_xrp", 0) == 0):
        st.error(f"Could not find active XRPL account `{wallet_query.strip()}`.")
    else:
        entity_badge = (
            f"🏷️ **{la['entity_name']}**"
            + (f" (`{la['domain']}`)" if la.get("domain") else "")
            if la.get("entity_name") and la["entity_name"] != "Unlabeled"
            else "👤 **Unlabeled Wallet**"
        )
        st.markdown(f"#### Wallet Analysis: `{la['account']}` — {entity_badge}")

        w_col1, w_col2, w_col3, w_col4, w_col5 = st.columns(5)
        if la.get("wealth_percentile") is not None:
            w_col1.metric(
                "Wealth Percentile",
                f"{la['wealth_percentile']:.4f}%",
                delta=f"Top {la['top_percentile']:.4f}% of XRPL",
            )
            w_col2.metric(
                "Global Rank",
                f"#{la['rank']:,}",
                delta=f"of {la['total_accounts']:,} wallets",
                delta_color="off",
            )
        else:
            w_col1.metric("Wealth Percentile", "Unranked")
            w_col2.metric("Global Rank", "N/A")

        w_col3.metric(
            "Liquid Balance",
            f"{la['liquid_xrp']:,.2f} XRP",
            delta=f"{la['pct_of_liquid_supply']:.4f}% of liquid XRP",
            delta_color="off",
        )
        w_col4.metric(
            "Total Holdings (incl. Escrow)",
            f"{la['total_xrp']:,.2f} XRP",
            delta=(
                f"{la['escrow_xrp']:,.0f} XRP in Escrow"
                if la.get("escrow_xrp", 0) > 0
                else "0 XRP in Escrow"
            ),
            delta_color="off",
        )
        w_col5.metric(
            "Rich-List Bracket",
            str(la.get("current_bracket", "Outside Top 10%")),
            delta=(
                f"+{la['xrp_to_next_bracket']:,.2f} XRP to {la['next_bracket_label']}"
                if la.get("next_bracket_label")
                else "Highest Tier (Top 0.01%)"
            ),
            delta_color="off",
        )

        # Progress bar toward next percentile bracket
        if la.get("next_bracket_label") and la.get("next_bracket_threshold_xrp"):
            target_xrp = float(la["next_bracket_threshold_xrp"])
            progress_ratio = min(1.0, max(0.0, float(la["liquid_xrp"]) / target_xrp)) if target_xrp > 0 else 0.0
            st.progress(
                progress_ratio,
                text=(
                    f"Progress toward **{la['next_bracket_label']}** threshold "
                    f"({la['liquid_xrp']:,.2f} / {target_xrp:,.2f} XRP — "
                    f"**{progress_ratio * 100:.1f}%** complete, "
                    f"needs **{la['xrp_to_next_bracket']:,.2f} XRP** more)"
                ),
            )
        else:
            st.success("🏆 This wallet is in the **Top 0.01%** (highest Rich-List percentile bracket on the XRP Ledger).")

        # Visual charts for the searched wallet
        wc1, wc2 = st.columns(2)
        with wc1:
            if snapshot.percentile_brackets:
                ladder_rows = []
                for b in reversed(snapshot.percentile_brackets):
                    achieved = la["liquid_xrp"] >= b.min_balance_xrp
                    ladder_rows.append(
                        {
                            "Tier": b.top_percentile_label,
                            "Threshold (XRP)": b.min_balance_xrp,
                            "Status": "Achieved ✅" if achieved else "Higher Tier 🎯",
                        }
                    )
                ladder_rows.append(
                    {
                        "Tier": "📍 This Wallet",
                        "Threshold (XRP)": max(0.000001, float(la["liquid_xrp"])),
                        "Status": "Searched Wallet 📍",
                    }
                )
                df_ladder = pd.DataFrame(ladder_rows)
                df_ladder.sort_values("Threshold (XRP)", ascending=True, inplace=True)

                fig_ladder = px.bar(
                    df_ladder,
                    x="Threshold (XRP)",
                    y="Tier",
                    color="Status",
                    orientation="h",
                    log_x=True,
                    title="Wallet Balance vs. Rich-List Percentile Thresholds (Log Scale)",
                    color_discrete_map={
                        "Achieved ✅": "#2ecc71",
                        "Higher Tier 🎯": "#34495e",
                        "Searched Wallet 📍": "#f39c12",
                    },
                    text=df_ladder["Threshold (XRP)"].map(lambda v: f"{v:,.2f} XRP"),
                )
                fig_ladder.update_traces(textposition="outside")
                fig_ladder.update_layout(height=400, yaxis_title="", xaxis_title="XRP Balance (Log Scale)")
                st.plotly_chart(fig_ladder, use_container_width=True)

        with wc2:
            if la.get("escrows"):
                df_esc = pd.DataFrame(la["escrows"])
                df_esc["finish_date"] = pd.to_datetime(df_esc["finish_after"], errors="coerce")
                df_esc_sorted = df_esc.sort_values("finish_date")
                fig_esc = px.bar(
                    df_esc_sorted,
                    x="finish_date",
                    y="amount_xrp",
                    title=f"Active Escrow Unlock Schedule ({len(df_esc)} Escrows | {la['escrow_xrp']:,.0f} XRP)",
                    labels={"finish_date": "Unlock Date (UTC)", "amount_xrp": "Escrowed XRP"},
                    color_discrete_sequence=["#3498db"],
                )
                fig_esc.update_layout(height=400)
                st.plotly_chart(fig_esc, use_container_width=True)
            elif snapshot.balance_ranges:
                wallet_tier = determine_balance_tier(float(la["liquid_xrp"]))
                df_tiers = pd.DataFrame(
                    [
                        {
                            "Balance Range": r.balance_range,
                            "Accounts": r.account_count,
                            "Highlight": "Your Wallet Tier 📍"
                            if r.balance_range == wallet_tier
                            else "Other Tiers",
                        }
                        for r in reversed(snapshot.balance_ranges)
                    ]
                )
                fig_tier_pos = px.bar(
                    df_tiers,
                    x="Balance Range",
                    y="Accounts",
                    color="Highlight",
                    log_y=True,
                    title=f"Global Account Distribution (Highlighted Tier: {wallet_tier} XRP)",
                    color_discrete_map={
                        "Your Wallet Tier 📍": "#f39c12",
                        "Other Tiers": "#4a69bd",
                    },
                )
                fig_tier_pos.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig_tier_pos, use_container_width=True)

        with st.expander("📋 View Detailed On-Ledger Metadata & Escrows"):
            m1, m2, m3, m4 = st.columns(4)
            m1.write(f"**Inception Date:** {str(la.get('inception') or 'N/A')[:10]}")
            m2.write(f"**Initial Balance:** {la.get('initial_balance') or 'N/A'} XRP")
            parent_str = la.get("parent") or "N/A"
            if la.get("parent_entity"):
                parent_str += f" ({la['parent_entity']})"
            m3.write(f"**Activating Parent:** `{parent_str}`")
            m4.write(f"**Owner Count / Seq:** {la.get('owner_count', 0)} objects / seq {la.get('sequence', 0):,}")

            if la.get("escrows"):
                st.dataframe(pd.DataFrame(la["escrows"]), use_container_width=True)

st.markdown("---")

# --- Global Ledger & Supply Metrics ---
st.subheader(f"🌐 Global XRP Ledger Supply & State (Ledger #{s.ledger_index:,})")
wallet_pct = (s.wallet_xrp / s.total_xrp * 100.0) if s.total_xrp else 0.0
escrow_pct = (s.escrow_xrp / s.total_xrp * 100.0) if s.total_xrp else 0.0

g1, g2, g3, g4, g5 = st.columns(5)
g1.metric("Total Active Wallets", f"{s.total_accounts:,}", delta=f"Avg: {s.average_balance_xrp:,.1f} XRP")
g2.metric("Total Remaining Supply", f"{s.total_xrp:,.0f} XRP", delta=f"-{s.burned_xrp:,.0f} XRP burned", delta_color="off")
g3.metric("Liquid in Wallets", f"{s.wallet_xrp:,.0f} XRP", delta=f"{wallet_pct:.2f}% of supply", delta_color="off")
g4.metric("Locked in Escrow", f"{s.escrow_xrp:,.0f} XRP", delta=f"{escrow_pct:.2f}% of supply", delta_color="off")
g5.metric("Snapshot Timestamp", str(s.close_time)[:19].replace("T", " "))

# --- Main Analytics Tabs ---
tab_percentiles, tab_distribution, tab_whales = st.tabs(
    [
        "📊 Rich-List Percentile Brackets",
        "⚖️ Balance Tiers & Supply Distribution",
        "🐋 Top Entities & Whale Leaderboard",
    ]
)

with tab_percentiles:
    st.markdown("#### Rich-List Percentile Thresholds (`Top 0.01%` to `Top 10%`)")
    if snapshot.percentile_brackets:
        df_pct = pd.DataFrame(
            [
                {
                    "Top %": b.top_percentile_label,
                    "Percentile Range": f"{b.rank_max_pct:g}% - {b.rank_min_pct:g}%",
                    "Cumulative Wallets": b.cumulative_accounts,
                    "Wallets in Bracket": b.bracket_accounts,
                    "Max Balance (XRP)": b.max_balance_xrp,
                    "Min Threshold (XRP)": b.min_balance_xrp,
                }
                for b in snapshot.percentile_brackets
            ]
        )

        p_col1, p_col2 = st.columns(2)
        with p_col1:
            fig_pct_thresh = px.bar(
                df_pct,
                x="Top %",
                y="Min Threshold (XRP)",
                log_y=True,
                color="Min Threshold (XRP)",
                color_continuous_scale="Viridis",
                title="Minimum XRP Required per Rich-List Percentile (Log Scale)",
                text=df_pct["Min Threshold (XRP)"].map(lambda v: f"{v:,.0f} XRP"),
            )
            fig_pct_thresh.update_traces(textposition="outside")
            fig_pct_thresh.update_layout(height=420, coloraxis_showscale=False)
            st.plotly_chart(fig_pct_thresh, use_container_width=True)

        with p_col2:
            fig_pct_accts = px.bar(
                df_pct,
                x="Top %",
                y=["Wallets in Bracket", "Cumulative Wallets"],
                barmode="group",
                title="Account Counts per Rich-List Percentile Bracket",
                labels={"value": "Number of Wallets", "variable": "Metric"},
            )
            fig_pct_accts.update_layout(height=420)
            st.plotly_chart(fig_pct_accts, use_container_width=True)

        df_pct_display = df_pct.copy()
        df_pct_display["Cumulative Wallets"] = df_pct_display["Cumulative Wallets"].map("{:,}".format)
        df_pct_display["Wallets in Bracket"] = df_pct_display["Wallets in Bracket"].map("{:,}".format)
        df_pct_display["Max Balance (XRP)"] = df_pct_display["Max Balance (XRP)"].map("{:,.2f} XRP".format)
        df_pct_display["Min Threshold (XRP)"] = df_pct_display["Min Threshold (XRP)"].map("{:,.2f} XRP".format)
        st.dataframe(df_pct_display, use_container_width=True, hide_index=True)

with tab_distribution:
    d_col1, d_col2 = st.columns([2, 1])
    with d_col1:
        if snapshot.balance_ranges:
            df_rng = pd.DataFrame(
                [
                    {
                        "Balance Range (XRP)": r.balance_range,
                        "# Accounts": r.account_count,
                        "% of Accounts": r.pct_of_accounts,
                        "Total XRP in Tier": r.total_xrp,
                        "% of Liquid XRP": r.pct_of_wallet_xrp,
                    }
                    for r in reversed(snapshot.balance_ranges)
                ]
            )
            fig_ineq = go.Figure()
            fig_ineq.add_trace(
                go.Bar(
                    x=df_rng["Balance Range (XRP)"],
                    y=df_rng["% of Accounts"],
                    name="% of All Wallets",
                    marker_color="#3498db",
                )
            )
            fig_ineq.add_trace(
                go.Bar(
                    x=df_rng["Balance Range (XRP)"],
                    y=df_rng["% of Liquid XRP"],
                    name="% of Liquid XRP Held",
                    marker_color="#e67e22",
                )
            )
            fig_ineq.update_layout(
                barmode="group",
                title="Wealth Concentration: % of Wallets vs. % of Liquid XRP Held by Balance Tier",
                xaxis_tickangle=-45,
                yaxis_title="Percentage (%)",
                height=450,
            )
            st.plotly_chart(fig_ineq, use_container_width=True)

    with d_col2:
        df_supply_pie = pd.DataFrame(
            [
                {"Category": "Liquid in Wallets", "XRP": s.wallet_xrp},
                {"Category": "Locked in Escrow", "XRP": s.escrow_xrp},
                {"Category": "Burned Fees", "XRP": s.burned_xrp},
            ]
        )
        fig_pie = px.pie(
            df_supply_pie,
            names="Category",
            values="XRP",
            hole=0.45,
            title="100B Max XRP Supply Breakdown",
            color="Category",
            color_discrete_map={
                "Liquid in Wallets": "#2ecc71",
                "Locked in Escrow": "#3498db",
                "Burned Fees": "#e74c3c",
            },
        )
        fig_pie.update_layout(height=450)
        st.plotly_chart(fig_pie, use_container_width=True)

    if snapshot.top10k_supply_brackets:
        df_whale_conc = pd.DataFrame(snapshot.top10k_supply_brackets)
        df_whale_conc["Tier"] = df_whale_conc["top_accounts"].map(lambda n: f"Top {n:,}")
        fig_conc = px.line(
            df_whale_conc,
            x="Tier",
            y=["pct_of_total_supply", "pct_of_liquid_supply"],
            markers=True,
            title="Cumulative Supply Controlled by Top Whale Tiers (Top 10 to Top 10,000)",
            labels={"value": "% of XRP Supply", "variable": "Supply Metric"},
        )
        fig_conc.update_layout(height=380)
        st.plotly_chart(fig_conc, use_container_width=True)

    if snapshot.balance_ranges:
        st.markdown("#### Full Balance Range Breakdown")
        df_rng_table = pd.DataFrame(
            [
                {
                    "Balance Range (XRP)": r.balance_range,
                    "Accounts": f"{r.account_count:,}",
                    "% of Accounts": f"{r.pct_of_accounts:.4f}%",
                    "Total XRP in Tier": f"{r.total_xrp:,.2f} XRP",
                    "% of Liquid XRP": f"{r.pct_of_wallet_xrp:.2f}%",
                }
                for r in snapshot.balance_ranges
            ]
        )
        st.dataframe(df_rng_table, use_container_width=True, hide_index=True)

with tab_whales:
    if snapshot.top_entities:
        df_ent = pd.DataFrame(
            [
                {
                    "Entity": e.entity_name,
                    "Domain": e.domain,
                    "Wallets": e.wallet_count,
                    "Liquid XRP": e.liquid_xrp,
                    "Escrowed XRP": e.escrow_xrp,
                    "Total XRP": e.total_xrp,
                    "% Total Supply": e.pct_of_total_supply,
                }
                for e in snapshot.top_entities
            ]
        )

        e_col1, e_col2 = st.columns([3, 2])
        with e_col1:
            fig_ent = px.bar(
                df_ent,
                x="Entity",
                y=["Liquid XRP", "Escrowed XRP"],
                barmode="stack",
                title=f"Top {len(df_ent)} Known Entities by Holdings (Liquid vs. Escrowed XRP)",
                labels={"value": "XRP Holdings", "variable": "Holding Type"},
                color_discrete_map={"Liquid XRP": "#2ecc71", "Escrowed XRP": "#3498db"},
            )
            fig_ent.update_layout(height=440, xaxis_tickangle=-35)
            st.plotly_chart(fig_ent, use_container_width=True)

        with e_col2:
            fig_tree = px.treemap(
                df_ent,
                path=["Entity"],
                values="Total XRP",
                color="% Total Supply",
                color_continuous_scale="Blues",
                title="Known Entity Share of XRP Holdings",
            )
            fig_tree.update_layout(height=440)
            st.plotly_chart(fig_tree, use_container_width=True)

        st.markdown(f"#### Top {len(df_ent)} Known Entities Table")
        df_ent_disp = df_ent.copy()
        df_ent_disp["Liquid XRP"] = df_ent_disp["Liquid XRP"].map("{:,.2f}".format)
        df_ent_disp["Escrowed XRP"] = df_ent_disp["Escrowed XRP"].map("{:,.2f}".format)
        df_ent_disp["Total XRP"] = df_ent_disp["Total XRP"].map("{:,.2f}".format)
        df_ent_disp["% Total Supply"] = df_ent_disp["% Total Supply"].map("{:.2f}%".format)
        st.dataframe(df_ent_disp, use_container_width=True, hide_index=True)

    st.markdown("---")
    sub_tab_tot, sub_tab_liq = st.tabs(
        [
            f"🏆 Top {len(snapshot.top_accounts_by_total)} Wallets by Total Holdings (Liquid + Escrow)",
            f"💧 Top {len(snapshot.top_accounts_by_liquid)} Wallets by Liquid Balance",
        ]
    )
    with sub_tab_tot:
        df_tot = pd.DataFrame(
            [
                {
                    "Rank": h.rank,
                    "Account": h.account,
                    "Entity": f"{h.entity_name} ({h.entity_desc})" if h.entity_desc else h.entity_name,
                    "Liquid XRP": f"{h.liquid_xrp:,.2f}",
                    "Escrowed XRP": f"{h.escrow_xrp:,.2f}",
                    "Total XRP": f"{h.total_xrp:,.2f}",
                    "% Total Supply": f"{h.pct_of_total_supply:.2f}%",
                }
                for h in snapshot.top_accounts_by_total
            ]
        )
        st.dataframe(df_tot, use_container_width=True, hide_index=True)

    with sub_tab_liq:
        df_liq = pd.DataFrame(
            [
                {
                    "Rank": h.rank,
                    "Account": h.account,
                    "Entity": f"{h.entity_name} ({h.entity_desc})" if h.entity_desc else h.entity_name,
                    "Liquid XRP": f"{h.liquid_xrp:,.2f}",
                    "Escrowed XRP": f"{h.escrow_xrp:,.2f}",
                    "% Wallet XRP": f"{h.pct_of_total_supply:.2f}%",
                }
                for h in snapshot.top_accounts_by_liquid
            ]
        )
        st.dataframe(df_liq, use_container_width=True, hide_index=True)
