# rippled-data: Architecture Decision Records (ADR) & Discussion Log

This document serves as the historical ledger of all architectural, data-engineering, and operational decisions made for the `rippled-data` XRP Ledger Rich-List & Holdings Analytics platform. Every major decision captures the problem context, alternatives evaluated, rationale, and consequences.

---

### Index of Decisions

1. [ADR-001: Decommissioning Self-Hosted `rippled` Infrastructure (`aws/`, `docker/`, `podman/`, `server/`)](#adr-001-decommissioning-self-hosted-rippled-infrastructure-aws-docker-podman-server)
2. [ADR-002: Concurrent Public Indexer & JSON-RPC Data Pipeline (`Rich-List.info` + `XRPSCAN` + `xrplcluster.com`)](#adr-002-concurrent-public-indexer--json-rpc-data-pipeline-rich-listinfo--xrpscan--xrplclustercom)
3. [ADR-003: Canonical Drops-to-XRP Normalization, Inclusive Percentile Ranking & Escrow/Entity Attribution](#adr-003-canonical-drops-to-xrp-normalization-inclusive-percentile-ranking--escrowentity-attribution)
4. [ADR-004: Interactive Wallet Wealth Percentile & Next-Tier Progression Engine](#adr-004-interactive-wallet-wealth-percentile--next-tier-progression-engine)
5. [ADR-005: Internal Network Streamlit Dashboard & Persistent User Systemd Service (`rippled-dashboard.service` on Port `8502`)](#adr-005-internal-network-streamlit-dashboard--persistent-user-systemd-service-rippled-dashboardservice-on-port-8502)

---

### ADR-001: Decommissioning Self-Hosted `rippled` Infrastructure (`aws/`, `docker/`, `podman/`, `server/`)
* **Date:** 2026-10-24
* **Status:** Accepted & Implemented
* **Context:** The legacy repository maintained four separate infrastructure stacks (`aws/` CloudFormation for `t3a.2xlarge` / `i3.large` NVMe EC2 instances, `docker/`, `podman/`, and `server/` systemd configs) solely to run a local `rippled` node. A local node was previously required because the legacy Python collector called `ledger_data` sequentially without filtering by `type="account"` and passed `limit=20000` (which `rippled` silently clamped to `256` JSON state objects per call, yielding only ~62 `AccountRoot` entries per request). Scanning the ledger required ~67,000+ sequential HTTP/WebSocket calls, writing 67,000 individual `.json` files to disk, and taking hours—causing public XRPL nodes to rate-limit requests or expire state `marker` cursors before completion.
* **Decision:** Delete `aws/`, `docker/`, `podman/`, `server/`, `log/`, and the legacy sequential collector scripts (`xrpl-rpc-get-ledger-data.py`, `xrpl-ws-get-ledger-data.py`, `xrpl-ledger-data-analysis.py`), replacing them with a zero-infrastructure architecture in [`src/xrpl_analytics.py`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py). Also replace the 98-package Fedora OS `pip freeze` dump in [`requirements.txt`](file:///home/simon/Code/Personal/rippled-data/requirements.txt) with the exact 5 runtime dependencies (`click`, `httpx`, `pandas`, `plotly`, `streamlit`).
* **Consequences:** Eliminates cloud compute costs, multi-hour ledger sync wait times, and tens of thousands of temporary JSON files on disk.

---

### ADR-002: Concurrent Public Indexer & JSON-RPC Data Pipeline (`Rich-List.info` + `XRPSCAN` + `xrplcluster.com`)
* **Date:** 2026-10-24
* **Status:** Accepted & Implemented
* **Context:** We evaluated three approaches for retrieving XRPL rich-list percentiles, global supply metrics, and top account holdings:
  1. *Sharded Async `ledger_data` Scanner*: Splitting the 256-bit XRPL state keyspace (`0000...` to `FFFF...`) across concurrent workers querying `type="account"` on public nodes. Still requires ~9,700 RPC calls (~20M ledger objects / 2,048 limit) and local aggregation of ~8.26M accounts.
  2. *Single-Source Public Indexer*: Relying on a single third-party REST endpoint. Fast, but lacks either full-ledger percentile thresholds or entity/escrow attribution depending on the provider.
  3. *Multi-Source Concurrent Public Indexer Pipeline*: Concurrently querying **Rich-List.info API** (`/api/stats`, `/api/stats/percentiles`, `/api/stats/balance-ranges`, `/api/richlist`), **XRPSCAN API** (`/api/v1/balances`, `/api/v1/fact/XRP`, `/api/v1/fact/ObjectCount`), and **Public XRPL JSON-RPC** (`https://xrplcluster.com`) using `asyncio` and `httpx`.
* **Decision:** Implement the concurrent multi-source pipeline in [`fetch_raw_data()`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py#L139-L183) with automatic cross-source fallback inside [`build_analytics()`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py#L202-L509) and optional offline snapshot persistence (`--save` / `--from-file`).
* **Consequences:** Full rich-list analytics execute in **~1.5–2 seconds** with zero local infrastructure while combining full-ledger percentile brackets (8.26M+ accounts) with top-10,000 entity attribution and escrow telemetry.

---

### ADR-003: Canonical Drops-to-XRP Normalization, Inclusive Percentile Ranking & Escrow/Entity Attribution
* **Date:** 2026-10-24
* **Status:** Accepted & Implemented
* **Context:** Reviewing the legacy `xrpl-ledger-data-analysis.py` revealed three major analytical defects:
  1. *Drops-vs-XRP ($10^6\times$) Unit Error*: Native XRPL balances are denominated in *drops* ($1\text{ XRP} = 1,000,000\text{ drops}$), but the legacy script never divided by $10^6$, reporting raw drops as `"XRP"`.
  2. *Top-1 Account Exclusion Bug*: Filtering pandas percentile ranks via `.between(rank_min_dec, rank_max_dec, inclusive="left")` used half-open intervals `[min, max)`, which excluded `rank_percent == 1.0` (the #1 richest wallet on the ledger) from `Top 100% - 99.99%`.
  3. *Escrow & Entity Blindness*: Inspecting only `AccountRoot.Balance` ignored ~31.5B XRP (~31.5% of total supply) locked in `Escrow` ledger objects and treated all addresses as anonymous strings rather than grouping known institutional/exchange entities.
* **Decision:**
  1. Normalize all drop values through [`drops_to_xrp()`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py#L28-L32).
  2. Anchor the `Top 100% - 99.99%` (`Top 0.01%`) upper bound to the #1 account's actual balance and compute exact cumulative and bracket-specific wallet counts across all 10 Rich-List tiers (`0.01%`, `0.1%`, `0.2%`, `0.5%`, `1%`, `2%`, `3%`, `4%`, `5%`, `10%`).
  3. Track **Liquid XRP**, **Escrowed XRP**, and **Total Holdings (`Liquid + Escrow`)** separately, and aggregate labeled wallets by entity (`Ripple`, `UPbit`, `Coinbase`, `Binance`, `Robinhood`, `Bithumb`, `Uphold`, `Kraken`, etc.).
* **Consequences:** All XRP figures, percentile boundaries, and supply percentages are mathematically accurate and reflect both circulating wallet balances and locked escrow holdings.

---

### ADR-004: Interactive Wallet Wealth Percentile & Next-Tier Progression Engine
* **Date:** 2026-10-24
* **Status:** Accepted & Implemented
* **Context:** Beyond static network tables, we needed the ability to look up any individual XRPL wallet address (`r...`) and immediately understand its standing on the ledger, its wealth percentile, its active escrows, and how much XRP is required to advance to the next Rich-List tier.
* **Decision:** Implement dedicated fast wallet resolution in [`fetch_wallet_raw()`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py#L186-L199) and enrich `looked_up_account` in [`build_analytics()`](file:///home/simon/Code/Personal/rippled-data/src/xrpl_analytics.py#L413-L496) to compute:
  - Exact `top_percentile` ($\frac{\text{rank}}{\text{total\_accounts}} \times 100$) and `wealth_percentile` ($100 - \text{top\_percentile}$).
  - Current Rich-List percentile bracket (`Top 0.01%` through `Top 10%`, or `Outside Top 10%`) and Balance Range Tier (`0 - 20` up to `1,000,000,000 - Infinity`).
  - Next tier target (`next_bracket_label`, `next_bracket_threshold_xrp`, and exact `xrp_to_next_bracket` delta).
  - Individual escrow objects with `amount_xrp`, `destination`, and `finish_after` unlock timestamps, plus XRPSCAN account metadata (entity name/domain, inception date, initial balance, activating parent account, owner count, and sequence).
* **Consequences:** Both the CLI (`--account <rAddress>`) and the Streamlit dashboard provide sub-second wallet wealth diagnostics and progression metrics.

---

### ADR-005: Internal Network Streamlit Dashboard & Persistent User Systemd Service (`rippled-dashboard.service` on Port `8502`)
* **Date:** 2026-10-24
* **Status:** Accepted & Implemented
* **Context:** Following the pattern established by `tradesies-dashboard.service` (which runs on internal network port `8501`), we wanted an always-on internal web dashboard for `rippled-data` to search wallet addresses, inspect wealth percentiles, and explore interactive charts across the LAN (`192.168.0.4`).
* **Decision:**
  1. Build [`src/dashboard.py`](file:///home/simon/Code/Personal/rippled-data/src/dashboard.py) using Streamlit and Plotly with 5-minute caching on global ledger telemetry (`@st.cache_data(ttl=300)`) and 60-second caching on individual wallet lookups (`@st.cache_data(ttl=60)`).
  2. Include interactive visualizations for wallet vs. Rich-List threshold ladders (log-scale), active wallet escrow unlock schedules, global balance range inequality (`% of Wallets` vs. `% of Liquid XRP`), 100B XRP supply donut charts, cumulative whale concentration curves (`Top 10` to `Top 10,000`), and entity holdings stacked bar/treemap charts.
  3. Provision a dedicated Python virtual environment (`.venv`) and deploy [`rippled-dashboard.service`](file:///home/simon/Code/Personal/rippled-data/rippled-dashboard.service) under `~/.config/systemd/user/rippled-dashboard.service` bound to `0.0.0.0:8502` with `Restart=on-failure`.
* **Consequences:** TheXRPL Rich-List & Wallet Analytics dashboard is continuously available at `http://localhost:8502` and `http://192.168.0.4:8502` without colliding with `tradesies` on port `8501`.
