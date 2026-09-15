from __future__ import annotations

import datetime as dt

import yfinance as yf


def fetch_recent_closes(ticker: str, lookback_days: int = 10) -> dict[dt.date, float]:
    """Fetch recent daily closes, split-adjusted (auto_adjust=True keeps the
    whole series consistent even if a future split occurs), keyed by trading date.
    """
    end = dt.date.today() + dt.timedelta(days=1)
    start = dt.date.today() - dt.timedelta(days=lookback_days)
    hist = yf.Ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
    out: dict[dt.date, float] = {}
    for idx, row in hist.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        out[d] = round(float(row["Close"]), 4)
    return out


def latest_close(ticker: str) -> tuple[dt.date, float]:
    closes = fetch_recent_closes(ticker, lookback_days=10)
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
        d, rate = latest_close("KRW=X")
        return {"date": d.isoformat(), "rate": rate}
    except Exception:  # noqa: BLE001
        return None
