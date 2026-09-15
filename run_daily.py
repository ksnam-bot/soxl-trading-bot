"""Entry point: run once a day (via GitHub Actions cron) to compute today's
buy/sell signals for every active portfolio, notify via KakaoTalk, and
publish a non-sensitive summary for the mobile dashboard (docs/latest.json).

Usage:
    python run_daily.py                # process + send Kakao notifications
    python run_daily.py --dry-run      # process + print to stdout only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from soxl_bot.calendar_utils import next_trading_day
from soxl_bot.config import load_portfolios, load_presets
from soxl_bot.engine import current_status_report, process_trading_day
from soxl_bot.notify import format_combined_message, format_portfolio_report
from soxl_bot.pricing import fetch_recent_closes, fetch_usd_krw
from soxl_bot.public_summary import (
    build_snapshot,
    config_snapshot,
    equity_snapshot,
    history_snapshot,
    portfolio_summary,
)
from soxl_bot.state import load_state, save_state

BASE_DIR = Path(__file__).parent


def run(dry_run: bool = False) -> int:
    presets = load_presets(BASE_DIR / "config" / "presets.json")
    portfolios = load_portfolios(BASE_DIR / "config" / "portfolios.json", presets, BASE_DIR)

    kakao_entries: list[tuple] = []
    public_summaries: list[dict] = []
    history_states: list[tuple] = []
    had_output = False

    for pf in portfolios:
        if not pf.active:
            continue

        state = load_state(pf.state_file)
        history_states.append((pf, state))
        closes = fetch_recent_closes(pf.ticker, lookback_days=14)
        if not closes:
            print(f"[{pf.id}] yfinance returned no data, skipping", file=sys.stderr)
            continue

        if state.as_of_date is None:
            print(f"[{pf.id}] state has no as_of_date; refusing to run blind. Seed state first.", file=sys.stderr)
            continue

        # Walk forward day by day from the day after as_of_date, in case the
        # job missed a run (weekend/outage), until we run out of fetched data.
        cursor = next_trading_day(state.as_of_date)
        last_report = None
        while cursor in closes:
            report = process_trading_day(pf.preset, state, cursor, closes[cursor])
            last_report = report
            cursor = next_trading_day(cursor)

        if last_report is not None:
            had_output = True
            save_state(state, pf.state_file)
            display_report = last_report
        else:
            print(f"[{pf.id}] no new trading day to process yet (waiting on {cursor}'s close) — showing current status")
            last_close = closes.get(state.as_of_date) or (closes[max(closes)] if closes else None)
            display_report = current_status_report(pf.preset, state, last_close)

        print("=" * 60)
        print(format_portfolio_report(pf, state, display_report))
        public_summaries.append(portfolio_summary(pf, state, display_report))
        if pf.kakao_enabled:
            kakao_entries.append((pf, state, display_report))

    docs_dir = BASE_DIR / "docs"
    docs_dir.mkdir(exist_ok=True)

    if public_summaries:
        fx = fetch_usd_krw()
        snapshot = build_snapshot(public_summaries, fx=fx)
        (docs_dir / "latest.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Settings rarely change, but keep the mobile "설정값 보기" page in sync every run.
    (docs_dir / "config.json").write_text(
        json.dumps(config_snapshot(portfolios), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (docs_dir / "history.json").write_text(
        json.dumps(history_snapshot(history_states), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (docs_dir / "equity.json").write_text(
        json.dumps(equity_snapshot(history_states), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if kakao_entries:
        combined_text = format_combined_message(kakao_entries)
        print("=" * 60)
        print("[combined kakao message]")
        print(combined_text)
        if not dry_run:
            from soxl_bot.kakao import send_daily_notification

            try:
                send_daily_notification(combined_text)
            except Exception as e:  # noqa: BLE001
                print(f"Kakao notification failed: {e}", file=sys.stderr)

    return 0 if had_output or not portfolios else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending KakaoTalk messages")
    args = parser.parse_args()
    raise SystemExit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
