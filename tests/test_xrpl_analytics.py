import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from xrpl_analytics import build_analytics, drops_to_xrp, format_report


class TestXrplAnalytics(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_raw = {
            "rl_stats": {
                "success": True,
                "data": {
                    "ledger_index": 107855218,
                    "ledger_date": "2026-10-23T19:00:10.000Z",
                    "accounts": 8000000,
                    "total_xrp": 99985000000.0,
                    "wallet_xrp": 68450000000.0,
                    "escrow_xrp": 31535000000.0,
                    "average_balance_xrp": 8556.25,
                },
            },
            "rl_percentiles": {
                "success": True,
                "data": [
                    {"percentile": "0.01 %", "account_count": 800, "balance_threshold_xrp": 3700000.0},
                    {"percentile": "0.1 %", "account_count": 8000, "balance_threshold_xrp": 270000.0},
                    {"percentile": "1 %", "account_count": 80000, "balance_threshold_xrp": 43000.0},
                ],
            },
            "rl_ranges": {
                "success": True,
                "data": [
                    {"account_count": 5, "balance_range": "1,000,000,000 - Infinity", "total_xrp": 8000000000.0},
                    {"account_count": 4000000, "balance_range": "0 - 20", "total_xrp": 25000000.0},
                ],
            },
            "rl_top": {
                "success": True,
                "data": [
                    {"rank": "1", "account_id": "rTopLiquid1", "balance_xrp": "1850000000.0"},
                ],
            },
            "xrpscan_balances": [
                {
                    "account": "rRippleEscrow1",
                    "balance": 500_000_000_000_000,
                    "escrow": 4_500_000_000_000_000,
                    "supply": 5_000_000_000_000_000,
                    "name": {"name": "Ripple", "desc": "11", "domain": "ripple.com"},
                },
                {
                    "account": "rTopLiquid1",
                    "balance": 1_850_000_000_000_000,
                    "escrow": 0,
                    "supply": 1_850_000_000_000_000,
                    "name": {"name": "Bithumb", "desc": "12", "domain": "bithumb.com"},
                },
            ],
            "xrpscan_xrp_fact": {
                "burned_coins": "15000000000000",
            },
            "rl_account": {
                "success": True,
                "data": {
                    "account_id": "rTopLiquid1",
                    "balance_xrp": "1850000000.0",
                    "rank": 1,
                },
            },
            "xrpscan_account": {
                "account": "rTopLiquid1",
                "accountName": {"name": "Bithumb", "domain": "bithumb.com"},
            },
        }

    def test_drops_to_xrp(self) -> None:
        self.assertEqual(drops_to_xrp(1_000_000), 1.0)
        self.assertEqual(drops_to_xrp("2500000"), 2.5)
        self.assertEqual(drops_to_xrp(None), 0.0)

    def test_build_analytics_percentile_brackets(self) -> None:
        snap = build_analytics(self.sample_raw, top_n=5)
        self.assertEqual(snap.supply.ledger_index, 107855218)
        self.assertEqual(snap.supply.burned_xrp, 15000000.0)
        self.assertEqual(len(snap.percentile_brackets), 3)

        first = snap.percentile_brackets[0]
        self.assertEqual(first.top_percentile_label, "Top 0.01%")
        self.assertEqual(first.rank_max_pct, 100.0)
        self.assertEqual(first.rank_min_pct, 99.99)
        self.assertEqual(first.cumulative_accounts, 800)
        self.assertEqual(first.bracket_accounts, 800)
        self.assertEqual(first.max_balance_xrp, 1850000000.0)
        self.assertEqual(first.min_balance_xrp, 3700000.0)

        second = snap.percentile_brackets[1]
        self.assertEqual(second.rank_max_pct, 99.99)
        self.assertEqual(second.rank_min_pct, 99.9)
        self.assertEqual(second.cumulative_accounts, 8000)
        self.assertEqual(second.bracket_accounts, 7200)
        self.assertEqual(second.max_balance_xrp, 3700000.0)
        self.assertEqual(second.min_balance_xrp, 270000.0)

    def test_top_accounts_and_entities(self) -> None:
        snap = build_analytics(self.sample_raw, top_n=5)
        self.assertEqual(snap.top_accounts_by_total[0].account, "rRippleEscrow1")
        self.assertEqual(snap.top_accounts_by_total[0].total_xrp, 5_000_000_000.0)
        self.assertEqual(snap.top_accounts_by_liquid[0].account, "rTopLiquid1")
        self.assertEqual(snap.top_accounts_by_liquid[0].liquid_xrp, 1_850_000_000.0)
        self.assertEqual(snap.top_entities[0].entity_name, "Ripple")
        self.assertIsNotNone(snap.looked_up_account)
        self.assertEqual(snap.looked_up_account["rank"], 1)
        self.assertAlmostEqual(snap.looked_up_account["wealth_percentile"], 99.9999875)
        self.assertEqual(snap.looked_up_account["current_bracket"], "Top 0.01%")
        self.assertIsNone(snap.looked_up_account["next_bracket_label"])

    def test_format_report_output(self) -> None:
        snap = build_analytics(self.sample_raw, top_n=5)
        report = format_report(snap)
        self.assertIn("#### Ledger & Supply Data ####", report)
        self.assertIn("Top 100% - 99.99% (Top 0.01%)", report)
        self.assertIn("rRippleEscrow1", report)
        self.assertIn("Bithumb", report)


if __name__ == "__main__":
    unittest.main()
