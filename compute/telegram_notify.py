"""Telegram notifier — lightweight notification gate for Theia.

Reads TELEGRAM_BOT_API_TOKEN from theia_net.get_secret().
Sends to TELEGRAM_CHAT_ID (default: read from secret, fallback to env).

All notifications are fire-and-forget (async thread).  Never block the main loop.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

# Add mcp/common to path for get_secret
theia_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(theia_root / "mcp" / "common"))
from theia_net import get_secret  # noqa: E402

try:
    import requests
except ImportError:
    # Fallback: warn and skip
    requests = None  # type: ignore

DEFAULT_TOKEN = get_secret("TELEGRAM_BOT_API_TOKEN", required=False) or ""
DEFAULT_CHAT_ID = get_secret("TELEGRAM_CHAT_ID", required=False) or os.environ.get("TELEGRAM_CHAT_ID", "")
DEFAULT_THREAD_ID = get_secret("TELEGRAM_THREAD_ID", required=False) or os.environ.get("TELEGRAM_THREAD_ID", "")


def _send_raw(token: str, chat_id: str, text: str, parse_mode: str = "HTML", message_thread_id: str = "") -> dict:
    """Synchronous send. Returns dict {ok, message_id, error}."""
    if requests is None:
        return {"ok": False, "error": "requests library not installed"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if message_thread_id:
        payload["message_thread_id"] = int(message_thread_id)
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"ok": False, "error": data.get("description", str(data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def notify(
    text: str,
    token: str = "",
    chat_id: str = "",
    message_thread_id: str = "",
    urgency: str = "normal",  # low | normal | high
    async_: bool = True,
) -> dict:
    """Send a Telegram notification.

    :param text: Message body (HTML allowed).
    :param token: Bot token (default from .secret).
    :param chat_id: Target chat (default from .secret/env).
    :param message_thread_id: Thread/topic ID for group/channel threads.
    :param urgency: 'high' prefixes 🚨, 'normal' prefixes ℹ️.
    :param async_: Fire-and-forget thread (True) or blocking (False).
    :return: Future-like dict if async_; real result if blocking.
    """
    tok = token or DEFAULT_TOKEN
    cid = chat_id or DEFAULT_CHAT_ID
    tid = message_thread_id or DEFAULT_THREAD_ID
    if not tok or not cid:
        return {"ok": False, "error": "missing TELEGRAM_BOT_API_TOKEN or TELEGRAM_CHAT_ID"}

    prefix = {"high": "🚨", "normal": "ℹ️", "low": "📊"}.get(urgency, "ℹ️")
    full_text = f"{prefix} <b>Theia</b>\n{text}"

    if async_:
        result_container: list[dict] = [{}]

        def _thread():
            result_container[0] = _send_raw(tok, cid, full_text, message_thread_id=tid)

        threading.Thread(target=_thread, daemon=True).start()
        return {"ok": True, "queued": True, "note": "async send"}

    return _send_raw(tok, cid, full_text, message_thread_id=tid)


def heartbeat_summary(
    open_positions: int,
    budget_used: dict[str, float],
    pending_hypotheses: int,
    token: str = "",
    chat_id: str = "",
) -> dict:
    """Formatted heartbeat digest."""
    lines = [
        f"📊 <b>Heartbeat</b>",
        f"Open positions: {open_positions}",
        f"Pending hypotheses: {pending_hypotheses}",
        f"Budget used:",
    ]
    for src, pct in budget_used.items():
        lines.append(f"  • {src}: {pct:.0%}")
    return notify("\n".join(lines), token=token, chat_id=chat_id, urgency="low")


def hypothesis_promoted(hypothesis_id: str, expectancy: float, profit_factor: float, n_trades: int) -> dict:
    """High-urgency: hypothesis cleared the gate."""
    text = (
        f"🚀 <b>Hypothesis Promoted</b>\n"
        f"ID: <code>{hypothesis_id}</code>\n"
        f"Expectancy: {expectancy:+.4f}\n"
        f"Profit Factor: {profit_factor:.2f}\n"
        f"Trades: {n_trades}\n"
        f"\nApprove to enable for live paper trading."
    )
    return notify(text, urgency="high")


def emergency_exit(trade_id: str, mint: str, reason: str, pnl: float) -> dict:
    """High-urgency: position closed on emergency."""
    text = (
        f"🚨 <b>Emergency Exit</b>\n"
        f"Trade: <code>{trade_id}</code>\n"
        f"Token: <code>{mint}</code>\n"
        f"Reason: {reason}\n"
        f"PnL: {pnl:+.4f} SOL"
    )
    return notify(text, urgency="high")


def api_source_banned(source: str, reason: str) -> dict:
    """High-urgency: API source down or rate-limited hard."""
    text = (
        f"🚨 <b>API Source Alert</b>\n"
        f"Source: {source}\n"
        f"Reason: {reason}\n"
        f"Theia has shifted to API-free work until recovery."
    )
    return notify(text, urgency="high")


def daily_digest(
    promoted: list[str],
    rejected: list[str],
    open_pnl: float,
    n_trades_today: int,
) -> dict:
    """Low-urgency: daily summary."""
    text = (
        f"📊 <b>Daily Digest</b>\n"
        f"Promoted: {len(promoted)}\n"
        f"Rejected: {len(rejected)}\n"
        f"Open PnL: {open_pnl:+.4f} SOL\n"
        f"Trades today: {n_trades_today}"
    )
    return notify(text, urgency="low")


if __name__ == "__main__":
    # Smoke test
    print("=== Theia Telegram Smoke Test ===")
    print(f"Token present: {bool(DEFAULT_TOKEN)}")
    print(f"Chat ID: {DEFAULT_CHAT_ID}")

    if not DEFAULT_TOKEN or not DEFAULT_CHAT_ID:
        print("ERROR: Set TELEGRAM_BOT_API_TOKEN and TELEGRAM_CHAT_ID in .secret or env")
        sys.exit(1)

    # 1. Simple ping
    print("\n[1] Sending ping...")
    r1 = notify("Smoke test: Theia notification system is online.", async_=False)
    print(f"Result: {r1}")

    # 2. Hypothesis promoted template
    print("\n[2] Sending hypothesis promoted template...")
    r2 = hypothesis_promoted("H-0007", 0.023, 1.45, 24)
    time.sleep(2)  # wait for async thread
    print(f"Result: {r2}")

    # 3. Heartbeat template
    print("\n[3] Sending heartbeat template...")
    r3 = heartbeat_summary(
        open_positions=2,
        budget_used={"dexdata": 0.45, "chainrpc": 0.32, "birdeye": 0.12},
        pending_hypotheses=3,
    )
    time.sleep(2)
    print(f"Result: {r3}")

    print("\n=== Smoke test complete ===")
