import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime
import pytz

# --- CONFIGURABLE PARAMETERS ---
SYMBOLS = ["HUT.TO", "SHOP.TO", "DEFI.NE", "DML.TO"]  # Add more TSX stocks here
POSITION_SIZE = 200
INTERVAL = "15m"
PERIOD = "1d"
TIMEZONE = "Canada/Eastern"

# --- TELEGRAM SETUP ---
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
            r = requests.post(url, data=payload)
            if r.status_code != 200:
                print("Telegram error:", r.text)
        except Exception as e:
            print("Telegram exception:", e)
    else:
        print("Missing Telegram credentials.")

# --- BACKTEST EACH STOCK ---
for symbol in SYMBOLS:
    print(f"\n📊 Processing {symbol}")
    try:
        data = yf.download(
            tickers=symbol,
            period=PERIOD,
            interval=INTERVAL,
            auto_adjust=True,
            progress=False
        )

        if data.empty:
            send_telegram_message(f"⚠️ No data for {symbol}")
            continue

        data.index = data.index.tz_localize('UTC').tz_convert(TIMEZONE)
        data["MA20"] = data["Close"].rolling(window=20).mean()
        data.dropna(inplace=True)

        if data.empty:
            send_telegram_message(f"⚠️ Insufficient data for {symbol}")
            continue

        latest = data.iloc[-1]
        timestamp = data.index[-1]
        price = float(latest["Close"])
        ma = float(latest["MA20"])

        trade_log = []
        position = None
        cash = 1000  # Not used in final logic, but kept for tracking
        total_profit = 0

        # --- BUY ---
        if price > ma and not position:
            qty = int(POSITION_SIZE // price)
            if qty > 0:
                position = {"buy_price": price, "qty": qty}
                trade_log.append(("BUY", timestamp, price, qty))
                send_telegram_message(
                    f"📈 *BUY* {symbol}\n🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n💵 Price: ${price:.2f}\n📦 Qty: {qty}"
                )

        # --- SELL ---
        if position and price < ma:
            qty = position["qty"]
            buy_price = position["buy_price"]
            profit = (price - buy_price) * qty
            trade_log.append(("SELL", timestamp, price, qty, profit))
            total_profit += profit
            send_telegram_message(
                f"📉 *SELL* {symbol}\n🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n💵 Price: ${price:.2f}\n📦 Qty: {qty}\n💰 Profit: ${profit:.2f}"
            )
            position = None

        # --- SUMMARY ---
        open_position_value = position["qty"] * price if position else 0
        final_value = cash + open_position_value
        roi = (final_value - 1000) / 1000 * 100

        summary_msg = (
            f"*{symbol} Intraday Summary*\n"
            f"🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
            f"📊 Price: ${price:.2f} | MA20: ${ma:.2f}\n"
            f"📦 Open Position: ${open_position_value:.2f}\n"
            f"📈 ROI: {roi:.2f}%\n"
            f"🔁 Trades: {len(trade_log)}"
        )
        send_telegram_message(summary_msg)

        # Optional plot
        plt.figure(figsize=(12, 5))
        plt.plot(data["Close"], label="Price", color="black")
        plt.plot(data["MA20"], label="MA20", color="blue", linestyle="--")
        for t in trade_log:
            if t[0] == "BUY":
                plt.scatter(t[1], t[2], marker="^", color="green", label="Buy", s=100)
            elif t[0] == "SELL":
                plt.scatter(t[1], t[2], marker="v", color="red", label="Sell", s=100)
        plt.title(f"{symbol} Intraday Backtest")
        plt.legend()
        plt.grid()
        plt.tight_layout()
        plt.savefig(f"{symbol.replace('.', '-')}_plot.png")

    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")
        send_telegram_message(f"❌ Error in processing {symbol}: {e}")
