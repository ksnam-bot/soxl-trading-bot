from __future__ import annotations

from .config import PortfolioConfig
from .engine import DayReport
from .state import PortfolioState


def format_portfolio_report(cfg: PortfolioConfig, state: PortfolioState, report: DayReport) -> str:
    lines: list[str] = []
    lines.append(f"[{cfg.name}] {report.trading_date.isoformat()} 종가 ${report.close:,.2f}")

    # 1) 어제 주문 체결 결과
    if report.filled_buy:
        b = report.filled_buy
        lines.append(f"✅ 매수 체결: {b.slot}번 티어 ${b.buy_price:,.2f} x {b.qty}주 (${b.cost:,.2f})")
    elif report.unfilled_buy_price is not None:
        lines.append(f"⏭ 매수 미체결 (지정가 ${report.unfilled_buy_price:,.2f} 위에서 마감)")

    for s in report.sells:
        tag = "🎯목표가 매도" if s.reason == "target" else "⏰기한 정리매도"
        lines.append(
            f"{tag}: {s.slot}번 티어 ${s.sell_price:,.2f} x {s.qty}주 "
            f"(매수 ${s.buy_price:,.2f}, 손익 ${s.profit:,.2f})"
        )

    if not report.filled_buy and report.unfilled_buy_price is None and not report.sells:
        lines.append("어제 새 체결 없음")

    # 2) 오늘 넣어야 할 주문
    lines.append("")
    if report.no_open_slot_today:
        lines.append("오늘 신규 매수 주문 없음 (전 티어 보유 중)")
    elif report.new_pending_ladder:
        lines.append(f"📋 오늘 LOC 매수 주문 ({report.new_pending_order.slot}번 티어):")
        for line in report.new_pending_ladder:
            lines.append(f"  ${line.price:,.2f} x {line.qty}주")
    else:
        lines.append("오늘 신규 매수 주문 없음")

    open_sell_lines = [
        f"  {p.slot}번 ${p.buy_price:,.2f}x{p.qty}주 → 목표 ${p.target_price:,.2f} (정리예정 {p.cutoff_date.isoformat()})"
        for p in state.open_positions
    ]
    if open_sell_lines:
        lines.append("📋 매도 대기 중인 보유 티어:")
        lines.extend(open_sell_lines)

    # 3) 현재 수익률
    holding_value = sum(p.qty * report.close for p in state.open_positions)
    total_value = state.cash + holding_value
    lines.append("")
    lines.append(f"💰 현금 ${state.cash:,.2f} + 평가 ${holding_value:,.2f} = 총 ${total_value:,.2f}")

    return "\n".join(lines)
