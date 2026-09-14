"""KakaoTalk '나에게 보내기' (memo API) notifier.

Requires a Kakao Developers app with the "카카오톡 메시지 > 나에게 보내기"
permission, plus a one-time browser OAuth login to obtain a refresh token
(see README.md / scripts/kakao_oauth_setup.md). After that, this module
refreshes the access token automatically on every run using the long-lived
refresh token.
"""
from __future__ import annotations

import json
import os

import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoError(RuntimeError):
    pass


def refresh_access_token(client_id: str, refresh_token: str, client_secret: str | None = None) -> dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = requests.post(TOKEN_URL, data=data, timeout=15)
    if resp.status_code != 200:
        raise KakaoError(f"Kakao token refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()


def send_text_to_me(access_token: str, text: str, web_url: str | None = None) -> None:
    template = {
        "object_type": "text",
        "text": text[:1900],  # safety net well under Kakao's memo text cap
        "link": {
            "web_url": web_url or "https://finance.yahoo.com/quote/SOXL",
            "mobile_web_url": web_url or "https://finance.yahoo.com/quote/SOXL",
        },
    }
    resp = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=15,
    )
    if resp.status_code != 200:
        raise KakaoError(f"Kakao send failed ({resp.status_code}): {resp.text}")


def send_daily_notification(text: str) -> None:
    """Reads credentials from environment variables (GitHub Actions secrets):
    KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN, and optionally KAKAO_CLIENT_SECRET.
    """
    client_id = os.environ["KAKAO_REST_API_KEY"]
    refresh_token = os.environ["KAKAO_REFRESH_TOKEN"]
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")

    tokens = refresh_access_token(client_id, refresh_token, client_secret)
    access_token = tokens["access_token"]
    send_text_to_me(access_token, text)

    # Kakao sometimes rotates the refresh token; if so, surface the new one
    # so the workflow can update the GitHub secret.
    new_refresh = tokens.get("refresh_token")
    if new_refresh and new_refresh != refresh_token:
        print(f"::warning::Kakao issued a new refresh_token. Update the KAKAO_REFRESH_TOKEN secret to: {new_refresh}")
