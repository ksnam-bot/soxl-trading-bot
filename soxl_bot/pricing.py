from __future__ import annotations

import datetime as dt
import math

import yfinance as yf

from .calendar_utils import market_close_utc

SETTLE_MARGIN = dt.timedelta(minutes=30)


def fetch_recent_closes(
    ticker: str, lookback_days: int = 10, require_complete_session: bool = True
) -> dict[dt.date, float]:
    """Fetch recent daily closes, split-adjusted (auto_adjust=True keeps the
    whole series consistent even if a future split occurs), keyed by trading date.

    Rows with no usable price (NaN/<=0) are dropped, and with
    require_complete_session a bar is kept only once its NYSE session has
    finished, so an unfinished day is never mistaken for a close.
    """
    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=lookback_days)
    hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
    now = dt.datetime.now(dt.timezone.utc)
    out: dict[dt.date, float] = {}
    for idx, row in hist.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        close = float(row["Close"])
        if not math.isfinite(close) or close <= 0:
            continue
        if require_complete_session and now < market_close_utc(d) + SETTLE_MARGIN:
            continue
        out[d] = round(close, 4)
    return out


def latest_close(
    ticker: str, lookback_days: int = 10, require_complete_session: bool = True
) -> tuple[dt.date, float]:
    closes = fetch_recent_closes(ticker, lookback_days, require_complete_session)
    if not closes:
        raise RuntimeError(f"yfinance returned no recent close data for {ticker}")
    last_date = max(closes)
    return last_date, closes[last_date]


def fetch_usd_krw() -> dict | None:
    """USD/KRW, reusing the same Yahoo Finance chart endpoint (ticker KRW=X).
    Returns None on failure rather than raising — a missing FX rate shouldn't
    stop the daily trading-signal run.
    """
    try:
        d, rate = latest_close("KRW=X", require_complete_session=False)
        return {"date": d.isoformat(), "rate": rate}
    except Exception:  # noqa: BLE001
        return None
