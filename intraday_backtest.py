import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, timedelta
import pytz

# --- CONFIGURABLE PARAMETERS ---
STOCK_SYMBOL = "AAPL"
BUDGET = 1000
POSITION_SIZE = 200  # Max per trade
INTERVAL = "15m"
PERIOD = "1d"  # 1 day of intraday data
TIMEZONE = "US/Eastern"

# --- TELEGRAM SETUP (use GitHub secrets or .env for security) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, data=payload)
            if response.status_code != 200:
                print("Telegram Error:", response.text)
        except Exception as e:
            print("Telegram Exception:", e)
    else:
        print("Telegram credentials missing.")

# --- FETCH INTRADAY DATA (15-min delay acceptable) ---
data = yf.download(
    tickers=STOCK_SYMBOL,
    period=PERIOD,
    interval=INTERVAL,
    auto_adjust=True,
    progress=False
)

# Calculate MA20
data["MA20"] = data["Close"].rolling(window=20).mean()
data.dropna(inplace=True)

if data.empty:
    print("No data retrieved.")
    send_telegram_message(f"⚠️ No data retrieved for {STOCK_SYMBOL} intraday.")
    exit()

# --- BACKTEST LOGIC (SINGLE RUN, LATEST DATA ONLY) ---
cash = BUDGET
positions = []
total_profit = 0
trade_log = []

latest = data.iloc[-1]
timestamp = data.index[-1].tz_convert(pytz.timezone(TIMEZONE))
price = float(latest["Close"])
ma = float(latest["MA20"])

# Buy condition: Price > MA
if price > ma and cash >= POSITION_SIZE:
    qty = int(POSITION_SIZE // price)
    if qty > 0:
        cost = qty * price
        positions.append({"buy_price": price, "qty": qty})
        cash -= cost
        trade_log.append(("BUY", timestamp, price, qty, None))
        send_telegram_message(f"📈 *BUY* {STOCK_SYMBOL}\n🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n💵 Price: ${price:.2f}\n📦 Qty: {qty}")

# Sell condition: Price < MA
for position in positions[:]:  # iterate copy
    if price < ma:
        qty = position["qty"]
        buy_price = position["buy_price"]
        profit = (price - buy_price) * qty
        cash += qty * price
        total_profit += profit
        trade_log.append(("SELL", timestamp, price, qty, profit))
        positions.remove(position)
        send_telegram_message(f"📉 *SELL* {STOCK_SYMBOL}\n🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n💵 Price: ${price:.2f}\n📦 Qty: {qty}\n💰 Profit: ${profit:.2f}")

# Final value
open_position_value = sum(p["qty"] * price for p in positions)
final_value = cash + open_position_value
roi = (final_value - BUDGET) / BUDGET * 100

# Send summary
summary_msg = (
    f"*Intraday Summary for {STOCK_SYMBOL}*\n"
    f"🕒 Time: {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
    f"📊 Price: ${price:.2f} | MA20: ${ma:.2f}\n\n"
    f"💰 Cash: ${cash:.2f}\n"
    f"📦 Open Position Value: ${open_position_value:.2f}\n"
    f"📈 Final Value: ${final_value:.2f}\n"
    f"📊 ROI: {roi:.2f}%\n"
    f"🔁 Trades: {len(trade_log)}"
)

print(summary_msg)
send_telegram_message(summary_msg)

# Save optional plot for GitHub Actions
plt.figure(figsize=(14, 6))
plt.plot(data["Close"], label="Price", color="black", alpha=0.7)
plt.plot(data["MA20"], label="MA20", color="blue", linestyle="--")

buy_points = [t for t in trade_log if t[0] == "BUY"]
sell_points = [t for t in trade_log if t[0] == "SELL"]

plt.scatter([t[1] for t in buy_points], [t[2] for t in buy_points], marker="^", color="green", label="Buy", s=100)
plt.scatter([t[1] for t in sell_points], [t[2] for t in sell_points], marker="v", color="red", label="Sell", s=100)

plt.title(f"{STOCK_SYMBOL} Intraday Backtest (Live - {INTERVAL})")
plt.xlabel("Time")
plt.ylabel("Price")
plt.legend()
plt.grid()
plt.tight_layout()
plt.savefig("intraday_plot.png")
