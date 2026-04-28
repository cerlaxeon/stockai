"""
Capitol Trade Monitor — Trump Ally Edition
==========================================
Watches STOCK Act public disclosures for 12 politicians
and sends Telegram alerts the moment new trades are filed.

Run locally:  python monitor.py
Deploy:       Railway (see README.md)
"""

import os
import json
import time
import logging
import requests
import schedule
from datetime import datetime, timezone
from pathlib import Path

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config — set these as environment variables on Railway ─────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
CHECK_INTERVAL_MIN = int(os.getenv("CHECK_INTERVAL_MIN", "60"))  # default hourly
SEEN_FILE          = Path(os.getenv("SEEN_FILE", "seen_trades.json"))

# ── Politicians to watch ───────────────────────────────────────────────────
WATCHLIST = [
    "Marjorie Taylor Greene",
    "Tommy Tuberville",
    "Rick Scott",
    "Ted Cruz",
    "Rand Paul",
    "Mike Johnson",
    "Josh Hawley",
    "Roger Marshall",
    "Ron Johnson",
    "Jim Jordan",
    "Matt Rosendale",
    "Dan Sullivan",
]

# Pre-build lowercase last-name lookup for fast matching
WATCHLIST_LASTNAMES = {name.split()[-1].lower(): name for name in WATCHLIST}

# ── Capitol Trades API ─────────────────────────────────────────────────────
CT_BASE    = "https://www.capitoltrades.com/api"
CT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "TradeMonitor/1.0 (educational/research use)",
}

# ── Telegram ───────────────────────────────────────────────────────────────
TG_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ══════════════════════════════════════════════════════════════════════════
# Persistent state — track which trade IDs we've already alerted on
# ══════════════════════════════════════════════════════════════════════════

def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_seen(seen: set) -> None:
    # Keep only the most recent 5,000 IDs to avoid unbounded growth
    ids = list(seen)[-5000:]
    SEEN_FILE.write_text(json.dumps(ids))


# ══════════════════════════════════════════════════════════════════════════
# Capitol Trades fetching
# ══════════════════════════════════════════════════════════════════════════

def fetch_recent_trades(page_size: int = 100) -> list[dict]:
    """
    Fetch the most recent trades from Capitol Trades public API.
    Returns a flat list of trade dicts.
    """
    url = f"{CT_BASE}/trades"
    params = {
        "pageSize": page_size,
        "order":    "filed_at_desc",
        "page":     1,
    }
    try:
        resp = requests.get(url, params=params, headers=CT_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # API shape varies — handle both {data: [...]} and bare list
        if isinstance(data, dict):
            return data.get("data", data.get("trades", []))
        return data if isinstance(data, list) else []
    except requests.RequestException as exc:
        log.error("Capitol Trades API error: %s", exc)
        return []


def is_watched(trade: dict) -> tuple[bool, str]:
    """
    Returns (True, full_name) if this trade belongs to a watched politician.
    Matches on last name (case-insensitive) to handle minor API name variations.
    """
    raw_name = (
        trade.get("politician", {}).get("name", "")
        if isinstance(trade.get("politician"), dict)
        else str(trade.get("politician", ""))
    )
    last = raw_name.split()[-1].lower() if raw_name else ""
    if last in WATCHLIST_LASTNAMES:
        return True, WATCHLIST_LASTNAMES[last]
    return False, ""


def trade_id(trade: dict) -> str:
    """Derive a stable unique ID for a trade record."""
    return str(
        trade.get("id")
        or trade.get("tradeId")
        or trade.get("_id")
        # fallback: hash of key fields
        or hash(frozenset({
            trade.get("politician", ""),
            trade.get("ticker", ""),
            trade.get("type", ""),
            trade.get("filedAt", trade.get("filed_at", "")),
        }))
    )


# ══════════════════════════════════════════════════════════════════════════
# Telegram messaging
# ══════════════════════════════════════════════════════════════════════════

TRADE_TYPE_EMOJI = {
    "purchase":     "🟢 BUY",
    "sale_full":    "🔴 SELL (full)",
    "sale_partial": "🟠 SELL (partial)",
    "exchange":     "🔄 EXCHANGE",
}

def format_message(trade: dict, pol_name: str) -> str:
    """Build a clean, readable Telegram alert message."""
    raw_type   = trade.get("type", trade.get("tradeType", "unknown"))
    trade_type = TRADE_TYPE_EMOJI.get(raw_type, f"📋 {raw_type.upper()}")

    ticker = (
        trade.get("ticker")
        or trade.get("asset", {}).get("ticker", "") if isinstance(trade.get("asset"), dict)
        else trade.get("asset", "")
    ) or "N/A"

    asset_name = (
        trade.get("asset", {}).get("name", "") if isinstance(trade.get("asset"), dict)
        else trade.get("assetName", "")
    ) or ticker

    amount = trade.get("amount") or trade.get("size") or "Not disclosed"

    filed_raw  = trade.get("filedAt") or trade.get("filed_at") or trade.get("filed", "")
    filed_date = filed_raw[:10] if filed_raw else "Unknown date"

    traded_raw  = trade.get("tradedAt") or trade.get("traded_at") or trade.get("transactionDate", "")
    traded_date = traded_raw[:10] if traded_raw else "Unknown"

    chamber = trade.get("politician", {}).get("chamber", "") if isinstance(trade.get("politician"), dict) else ""
    state   = trade.get("politician", {}).get("state", "") if isinstance(trade.get("politician"), dict) else ""
    party   = trade.get("politician", {}).get("party", "R") if isinstance(trade.get("politician"), dict) else "R"

    ct_url = f"https://www.capitoltrades.com/politicians/{trade.get('politician', {}).get('id', '')}" \
             if isinstance(trade.get("politician"), dict) else "https://www.capitoltrades.com"

    lines = [
        f"🏛 *CAPITOL TRADE ALERT*",
        f"",
        f"👤 *{pol_name}*  {party} · {state or chamber}",
        f"",
        f"{trade_type}",
        f"📈 *{ticker}* — {asset_name}",
        f"💰 Amount: `{amount}`",
        f"",
        f"📅 Traded: `{traded_date}`",
        f"📋 Filed:  `{filed_date}`",
        f"",
        f"⚠️ _STOCK Act disclosures may be up to 45 days late._",
        f"[View on Capitol Trades]({ct_url})",
    ]
    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """Send a Markdown-formatted message via Telegram Bot API."""
    url  = f"{TG_BASE}/sendMessage"
    data = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=data, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Telegram send failed: %s", exc)
        return False


def send_startup_message() -> None:
    """Notify you when the monitor comes online."""
    names = "\n".join(f"  • {n}" for n in WATCHLIST)
    msg = (
        f"🚀 *Trade Monitor is online*\n\n"
        f"Checking Capitol Trades every *{CHECK_INTERVAL_MIN} minutes*.\n\n"
        f"Watching:\n{names}\n\n"
        f"_You'll be notified the moment a new trade is filed._"
    )
    send_telegram(msg)


# ══════════════════════════════════════════════════════════════════════════
# Core check loop
# ══════════════════════════════════════════════════════════════════════════

def check_trades() -> None:
    log.info("Checking Capitol Trades...")
    seen   = load_seen()
    trades = fetch_recent_trades()

    if not trades:
        log.warning("No trades returned — API may be down or rate-limiting.")
        return

    new_count = 0
    for trade in trades:
        tid = trade_id(trade)
        if tid in seen:
            continue

        watched, pol_name = is_watched(trade)
        if not watched:
            seen.add(tid)
            continue

        # New trade from a watched politician!
        log.info("NEW TRADE: %s — %s %s", pol_name,
                 trade.get("type", "?"), trade.get("ticker", "?"))
        msg = format_message(trade, pol_name)
        if send_telegram(msg):
            log.info("Alert sent via Telegram.")
        else:
            log.error("Failed to send Telegram alert.")

        seen.add(tid)
        new_count += 1

    save_seen(seen)
    log.info("Check complete. %d new alert(s) sent. Total seen: %d", new_count, len(seen))


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    log.info("Starting Capitol Trade Monitor")
    log.info("Watching %d politicians", len(WATCHLIST))
    log.info("Check interval: every %d minutes", CHECK_INTERVAL_MIN)

    # ── Pre-flight checks ──────────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Add it in Railway → Variables.")
        raise SystemExit(1)
    if not TELEGRAM_CHAT_ID:
        log.critical("TELEGRAM_CHAT_ID is not set. Add it in Railway → Variables.")
        raise SystemExit(1)

    log.info("Bot token: %s...%s (length %d)",
             TELEGRAM_BOT_TOKEN[:8], TELEGRAM_BOT_TOKEN[-4:], len(TELEGRAM_BOT_TOKEN))
    log.info("Chat ID:   %s", TELEGRAM_CHAT_ID)

    # Validate Telegram credentials before starting
    test_url = f"{TG_BASE}/getMe"
    try:
        r = requests.get(test_url, timeout=10)
        if r.status_code == 401:
            log.critical("TELEGRAM_BOT_TOKEN is INVALID (401 Unauthorized).")
            log.critical("Get a fresh token from @BotFather → /newbot or /token")
            raise SystemExit(1)
        r.raise_for_status()
        bot_name = r.json()["result"]["username"]
        log.info("Telegram bot connected: @%s", bot_name)
    except SystemExit:
        raise
    except Exception as exc:
        log.critical("Cannot reach Telegram API: %s", exc)
        log.critical("Check Railway network settings or try redeploying.")
        raise SystemExit(1)

    # Test-send to catch wrong Chat ID early
    log.info("Sending test message to chat ID %s...", TELEGRAM_CHAT_ID)
    ok = send_telegram(
        "🔧 *Setup test* — if you see this, everything is working correctly.\n\n"
        "Your Capitol Trade Monitor is about to go live."
    )
    if not ok:
        log.critical("Could not send to TELEGRAM_CHAT_ID=%s", TELEGRAM_CHAT_ID)
        log.critical("Fix: open Telegram, search your bot username, press START, then redeploy.")
        raise SystemExit(1)
    log.info("Test message delivered successfully.")

    send_startup_message()

    # Run immediately on start, then on schedule
    check_trades()
    schedule.every(CHECK_INTERVAL_MIN).minutes.do(check_trades)

    log.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
