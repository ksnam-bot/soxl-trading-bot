from __future__ import annotations

from .config import PortfolioConfig
from .engine import DayReport
from .state import PortfolioState


def _fill_summary(report: DayReport) -> list[str]:
    """어제 주문 체결 결과 (매수 체결/미체결, 매도 체결)."""
    lines: list[str] = []
    if report.filled_buy:
        b = report.filled_buy
        lines.append(f"✅ 매수 체결: {b.slot}번 티어 ${b.buy_price:,.2f} x {b.qty}주 (${b.cost:,.2f})")
    elif report.unfilled_buy_price is not None:
        lines.append(f"⏭ 매수 미체결 (지정가 ${report.unfilled_buy_price:,.2f} 위에서 마감)")

    for s in report.sells:
        tag = "🎯목표가 매도 체결" if s.reason == "target" else "⏰기한 정리매도 체결"
        lines.append(
            f"{tag}: {s.slot}번 티어 ${s.sell_price:,.2f} x {s.qty}주 "
            f"(매수 ${s.buy_price:,.2f}, 손익 ${s.profit:,.2f})"
        )

    if not lines:
        lines.append("어제 새 체결 없음")
    return lines


def _buy_order_lines(report: DayReport) -> list[str]:
    """오늘 넣어야 할 매수 LOC 주문 (라더링 가격x수량)."""
    if report.no_open_slot_today:
        return ["매수 주문 없음 (전 티어 보유 중)"]
    if not report.new_pending_order or not report.new_pending_ladder:
        return ["매수 주문 없음"]
    lines = [f"📋 매수 주문 ({report.new_pending_order.slot}번 티어):"]
    for l in report.new_pending_ladder:
        lines.append(f"  ${l.price:,.2f} x {l.qty}주")
    return lines


def _sell_order_lines(state: PortfolioState) -> list[str]:
    """오늘 넣어야 할 매도 LOC 주문 (보유 중인 모든 티어, 목표가 지정가 매도)."""
    if not state.open_positions:
        return ["매도 주문 없음 (보유 티어 없음)"]
    lines = ["📋 매도 주문 (보유 티어 전부, 목표가 지정가):"]
    for p in state.open_positions:
        lines.append(
            f"  {p.slot}번 ${p.target_price:,.2f} x {int(p.qty)}주 "
            f"(매수 ${p.buy_price:,.2f}, 정리예정일 {p.cutoff_date.isoformat()})"
        )
    return lines


def format_portfolio_report(cfg: PortfolioConfig, state: PortfolioState, report: DayReport) -> str:
    """단일 계좌용 상세 리포트 (콘솔 출력/디버깅용)."""
    lines: list[str] = [f"[{cfg.name}] {report.trading_date.isoformat()} 종가 ${report.close:,.2f}"]
    lines += _fill_summary(report)
    lines.append("")
    lines += _buy_order_lines(report)
    lines += _sell_order_lines(state)

    holding_value = sum(p.qty * report.close for p in state.open_positions)
    total_value = state.cash + holding_value
    lines.append("")
    lines.append(f"💰 현금 ${state.cash:,.2f} + 평가 ${holding_value:,.2f} = 총 ${total_value:,.2f}")
    return "\n".join(lines)


def format_combined_message(entries: list[tuple[PortfolioConfig, PortfolioState, DayReport]]) -> str:
    """모든 활성 계좌를 하나의 카카오톡 메시지로 묶고, 맨 아래에 합산 총자산을 붙인다."""
    if not entries:
        return ""

    trading_date = entries[0][2].trading_date.isoformat()
    lines: list[str] = [f"📊 SOXL 매매 신호 {trading_date}"]

    total_cash = 0.0
    total_value = 0.0
    per_portfolio_totals: list[str] = []

    for cfg, state, report in entries:
        label = cfg.short_label or cfg.name
        lines.append("")
        lines.append(f"[{label}] 종가 ${report.close:,.2f}")
        lines += _fill_summary(report)
        lines += _buy_order_lines(report)
        lines += _sell_order_lines(state)

        holding_value = sum(p.qty * report.close for p in state.open_positions)
        value = state.cash + holding_value
        total_cash += state.cash
        total_value += value
        per_portfolio_totals.append(f"{label} ${value:,.0f}")

    lines.append("")
    lines.append(f"💰 합산 총자산 ${total_value:,.0f} (현금 ${total_cash:,.0f})")
    lines.append("   " + " + ".join(per_portfolio_totals))

    return "\n".join(lines)
