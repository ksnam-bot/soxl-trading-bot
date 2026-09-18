"""Small always-on relay so the dashboard can show REAL Toss Securities
holdings, without the Toss API credentials ever touching the browser or the
public GitHub repo.

Why this exists: Toss's Open API requires every caller's IP to be on an
allow-list, so it can't be called directly from a phone browser (roaming IP)
or from GitHub Actions (a fresh IP every run). This relay runs on one fixed
box (its IP is the one thing registered with Toss) and exposes a narrow,
separately-authenticated HTTP endpoint the dashboard calls instead.

Phase 1 scope: READ-ONLY (accounts/holdings). No order placement here on
purpose — that's a deliberate later step once this pipe is proven reliable.
"""
from __future__ import annotations

import os
import time

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

TOSS_BASE = "https://openapi.tossinvest.com"

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]
RELAY_SHARED_SECRET = os.environ["RELAY_SHARED_SECRET"]  # dashboard must send this back
DEFAULT_ACCOUNT_SEQ = os.environ.get("TOSS_ACCOUNT_SEQ")  # optional; auto-discovered if unset

app = FastAPI(title="SOXL Toss relay (read-only)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the bearer secret is the real access control, not CORS
    allow_methods=["GET"],
    allow_headers=["*"],
)

_token_cache: dict = {"value": None, "expires_at": 0.0}
_account_cache: dict = {"seq": DEFAULT_ACCOUNT_SEQ}


def _require_relay_secret(authorization: str | None) -> None:
    if not authorization or authorization != f"Bearer {RELAY_SHARED_SECRET}":
        raise HTTPException(status_code=401, detail="unauthorized")


def _get_access_token() -> str:
    now = time.time()
    if _token_cache["value"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["value"]

    resp = requests.post(
        f"{TOSS_BASE}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10,
    )
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Toss token request failed: {resp.status_code} {resp.text}")
    data = resp.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 300)
    return _token_cache["value"]


def _get_account_seq(token: str) -> str:
    if _account_cache["seq"]:
        return str(_account_cache["seq"])

    resp = requests.get(f"{TOSS_BASE}/api/v1/accounts", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Toss accounts request failed: {resp.status_code} {resp.text}")
    accounts = resp.json().get("result", [])
    if not accounts:
        raise HTTPException(status_code=502, detail="Toss returned no brokerage accounts for this app")
    _account_cache["seq"] = accounts[0]["accountSeq"]
    return str(_account_cache["seq"])


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/toss/holdings")
def toss_holdings(authorization: str | None = Header(None), symbol: str | None = None):
    """Real holdings from the user's own Toss brokerage account.
    Pass ?symbol=SOXL to filter to just this position (recomputes the
    summary fields for that symbol too, per Toss's own API behavior).
    """
    _require_relay_secret(authorization)
    token = _get_access_token()
    account_seq = _get_account_seq(token)

    headers = {"Authorization": f"Bearer {token}", "X-Tossinvest-Account": account_seq}
    params = {"symbol": symbol} if symbol else {}
    resp = requests.get(f"{TOSS_BASE}/api/v1/holdings", headers=headers, params=params, timeout=10)
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"Toss holdings request failed: {resp.status_code} {resp.text}")
    return resp.json().get("result", {})
