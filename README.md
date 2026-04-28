# Capitol Trade Monitor — Setup Guide

Monitors STOCK Act public trade disclosures for Trump-allied politicians
and sends you a Telegram message the moment a new trade is filed.

**Cost:** Free (Telegram) + $0–$5/month (Railway hosting)
**Tech needed:** None — just follow these steps

---

## Step 1 — Create your Telegram bot (5 minutes)

1. Open Telegram and search for **@BotFather**
2. Send it the message: `/newbot`
3. It will ask for a name — type anything, e.g. `Trade Alert Bot`
4. It will ask for a username — must end in `bot`, e.g. `mytradebot`
5. BotFather sends you a **token** that looks like:
   ```
   7412398456:AAFabcXYZ123randomcharactershere
   ```
   **Save this — it's your `TELEGRAM_BOT_TOKEN`**

6. Now get your **Chat ID**:
   - Search for **@userinfobot** in Telegram
   - Send it any message (e.g. `/start`)
   - It replies with your ID number, e.g. `391847562`
   - **Save this — it's your `TELEGRAM_CHAT_ID`**

7. Start a chat with your new bot: search for it by its username and press **Start**
   (The bot can't message you first — you have to initiate)

---

## Step 2 — Deploy to Railway (10 minutes)

Railway is a cloud platform with a free tier. Your script will run 24/7 there.

### 2a. Create a GitHub repo

1. Go to [github.com](https://github.com) and sign in (or create a free account)
2. Click the **+** button → **New repository**
3. Name it `trade-monitor`, set it to **Private**, click **Create**
4. Upload all four files from this folder:
   - `monitor.py`
   - `requirements.txt`
   - `Procfile`
   - `railway.toml`

   (Click "uploading an existing file" on the GitHub page)

### 2b. Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `trade-monitor` repository
4. Railway detects the Python project automatically

### 2c. Add your environment variables (secrets)

In Railway, go to your project → **Variables** tab → add these:

| Variable name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |
| `TELEGRAM_CHAT_ID` | Your ID from @userinfobot |
| `CHECK_INTERVAL_MIN` | `60` (checks every hour — lower = more API calls) |

Click **Save** — Railway automatically restarts with the new variables.

### 2d. Confirm it's running

1. Go to the **Deployments** tab in Railway
2. Click the latest deployment → **View logs**
3. You should see lines like:
   ```
   Starting Capitol Trade Monitor
   Watching 12 politicians
   Telegram bot connected: @yourbot
   Checking Capitol Trades...
   Check complete. 0 new alert(s) sent.
   ```
4. Within a minute, you'll get a Telegram message saying the monitor is online

---

## Step 3 — Test it works

Send your bot a message in Telegram — if you got the startup message in Step 2d,
everything is working. You'll now receive alerts like:

```
🏛 CAPITOL TRADE ALERT

👤 Tommy Tuberville  R · AL

🟢 BUY
📈 NVDA — Nvidia Corp
💰 Amount: $15,001 – $50,000

📅 Traded: 2025-03-10
📋 Filed:  2025-03-12

⚠️ STOCK Act disclosures may be up to 45 days late.
View on Capitol Trades
```

---

## Understanding alerts

- **Filed date** = when the disclosure was submitted to Congress (this triggers your alert)
- **Traded date** = when the actual transaction happened (may be weeks earlier)
- **STOCK Act law** gives politicians up to 45 days to disclose after a trade
- Amounts are reported in ranges — exact figures aren't disclosed
- All data comes from the official public [Capitol Trades](https://www.capitoltrades.com) database

---

## Adjusting the watchlist

Open `monitor.py` and edit the `WATCHLIST` variable at the top:

```python
WATCHLIST = [
    "Marjorie Taylor Greene",
    "Tommy Tuberville",
    # add or remove names here
]
```

Then push the updated file to GitHub — Railway redeploys automatically.

---

## Troubleshooting

**No startup message received**
- Make sure you started a chat with your bot first (search its username, press Start)
- Double-check `TELEGRAM_CHAT_ID` in Railway variables

**"Telegram bot token is invalid" in logs**
- Recheck your token — it should look like `1234567890:AAF...`

**"No trades returned" in logs**
- Capitol Trades API may be temporarily down — the monitor retries automatically
- Check [capitoltrades.com](https://www.capitoltrades.com) to confirm the site is up

**Railway free tier limit**
- Railway's free tier gives ~500 hours/month — enough for one always-on worker
- If you hit limits, upgrade to Hobby plan ($5/month)

---

## Legal note

All trade data is legally required public information under the STOCK Act (2012).
This tool only reads public disclosures — it performs no scraping and makes no
trades on your behalf. This is not financial advice.
