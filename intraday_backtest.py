import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime
import pytz
import numpy as np

# --- CONFIGURABLE PARAMETERS ---
SYMBOLS = ["HUT.TO", "SHOP.TO", "DEFI.NE", "DML.TO"]
POSITION_SIZE = 200
INTERVAL = "15m"
PERIOD = "1d"
TIMEZONE = "Canada/Eastern"

# Strategy parameters
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_WINDOW = 20
BOLLINGER_STD = 2

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

def calculate_rsi(data, window=14):
    """Calculate RSI without external libraries"""
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data, fast=12, slow=26, signal=9):
    """Calculate MACD without external libraries"""
    exp1 = data['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = data['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def calculate_bollinger_bands(data, window=20, std=2):
    """Calculate Bollinger Bands without external libraries"""
    sma = data['Close'].rolling(window=window).mean()
    rolling_std = data['Close'].rolling(window=window).std()
    upper = sma + (rolling_std * std)
    lower = sma - (rolling_std * std)
    return upper, sma, lower

def calculate_atr(data, window=14):
    """Calculate ATR without external libraries"""
    high_low = data['High'] - data['Low']
    high_close = np.abs(data['High'] - data['Close'].shift())
    low_close = np.abs(data['Low'] - data['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=window).mean()

def calculate_indicators(df):
    """Calculate all technical indicators without external libraries"""
    # Moving Averages
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    
    # RSI
    df['RSI'] = calculate_rsi(df)
    
    # MACD
    df['MACD'], df['MACD_Signal'] = calculate_macd(df, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    
    # Bollinger Bands
    df['UpperBand'], df['MiddleBand'], df['LowerBand'] = calculate_bollinger_bands(df, BOLLINGER_WINDOW, BOLLINGER_STD)
    
    # ATR for volatility
    df['ATR'] = calculate_atr(df)
    
    return df.dropna()

def generate_signal(row, position):
    """Generate trading signals based on multiple indicators"""
    buy_signals = 0
    sell_signals = 0
    
    # MA Crossover
    if row['Close'] > row['MA20'] and row['MA20'] > row['MA50']:
        buy_signals += 1
    elif row['Close'] < row['MA20'] and row['MA20'] < row['MA50']:
        sell_signals += 1
    
    # RSI
    if row['RSI'] < RSI_OVERSOLD:
        buy_signals += 1
    elif row['RSI'] > RSI_OVERBOUGHT:
        sell_signals += 1
    
    # MACD
    if row['MACD'] > row['MACD_Signal']:
        buy_signals += 1
    elif row['MACD'] < row['MACD_Signal']:
        sell_signals += 1
    
    # Bollinger Bands
    if row['Close'] < row['LowerBand']:
        buy_signals += 1
    elif row['Close'] > row['UpperBand']:
        sell_signals += 1
    
    # Determine final signal (weighted)
    if buy_signals >= 3 and not position:
        return "BUY"
    elif sell_signals >= 3 and position:
        return "SELL"
    return None

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
        data = calculate_indicators(data)

        if data.empty:
            send_telegram_message(f"⚠️ Insufficient data for {symbol}")
            continue

        latest = data.iloc[-1]
        timestamp = data.index[-1]
        price = float(latest["Close"])

        trade_log = []
        position = None
        cash = 1000  # Starting capital
        total_profit = 0

        # Iterate through each candle
        for i in range(1, len(data)):
            current = data.iloc[i]
            
            signal = generate_signal(current, position)
            
            # Execute trades
            if signal == "BUY" and not position:
                qty = int(POSITION_SIZE // current["Close"])
                if qty > 0:
                    position = {
                        "buy_price": current["Close"],
                        "qty": qty,
                        "stop_loss": current["Close"] - (2 * current["ATR"]),
                        "take_profit": current["Close"] + (3 * current["ATR"])
                    }
                    trade_log.append(("BUY", current.name, current["Close"], qty))
                    send_telegram_message(
                        f"📈 *BUY* {symbol}\n"
                        f"🕒 {current.name.strftime('%Y-%m-%d %H:%M')}\n"
                        f"💵 Price: ${current['Close']:.2f}\n"
                        f"📦 Qty: {qty}\n"
                        f"🛑 Stop Loss: ${position['stop_loss']:.2f}\n"
                        f"🎯 Take Profit: ${position['take_profit']:.2f}"
                    )
            
            elif position:
                # Check stop loss/take profit
                if current["Low"] <= position["stop_loss"]:
                    # Stop loss hit
                    profit = (position["stop_loss"] - position["buy_price"]) * position["qty"]
                    trade_log.append(("SELL", current.name, position["stop_loss"], position["qty"], profit))
                    total_profit += profit
                    send_telegram_message(
                        f"🛑 *STOP LOSS* {symbol}\n"
                        f"🕒 {current.name.strftime('%Y-%m-%d %H:%M')}\n"
                        f"💵 Price: ${position['stop_loss']:.2f}\n"
                        f"📦 Qty: {position['qty']}\n"
                        f"💰 Profit: ${profit:.2f}"
                    )
                    position = None
                
                elif current["High"] >= position["take_profit"]:
                    # Take profit hit
                    profit = (position["take_profit"] - position["buy_price"]) * position["qty"]
                    trade_log.append(("SELL", current.name, position["take_profit"], position["qty"], profit))
                    total_profit += profit
                    send_telegram_message(
                        f"🎯 *TAKE PROFIT* {symbol}\n"
                        f"🕒 {current.name.strftime('%Y-%m-%d %H:%M')}\n"
                        f"💵 Price: ${position['take_profit']:.2f}\n"
                        f"📦 Qty: {position['qty']}\n"
                        f"💰 Profit: ${profit:.2f}"
                    )
                    position = None
                
                elif signal == "SELL":
                    # Indicator-based sell
                    profit = (current["Close"] - position["buy_price"]) * position["qty"]
                    trade_log.append(("SELL", current.name, current["Close"], position["qty"], profit))
                    total_profit += profit
                    send_telegram_message(
                        f"📉 *SELL* {symbol}\n"
                        f"🕒 {current.name.strftime('%Y-%m-%d %H:%M')}\n"
                        f"💵 Price: ${current['Close']:.2f}\n"
                        f"📦 Qty: {position['qty']}\n"
                        f"💰 Profit: ${profit:.2f}"
                    )
                    position = None

        # --- SUMMARY ---
        open_position_value = position["qty"] * price if position else 0
        final_value = cash + total_profit + open_position_value
        roi = (final_value - 1000) / 1000 * 100

        summary_msg = (
            f"*{symbol} Intraday Summary*\n"
            f"🕒 {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
            f"📊 Price: ${price:.2f}\n"
            f"📦 Open Position: ${open_position_value:.2f}\n"
            f"💰 Total Profit: ${total_profit:.2f}\n"
            f"📈 ROI: {roi:.2f}%\n"
            f"🔁 Trades: {len(trade_log)}"
        )
        send_telegram_message(summary_msg)

        # Plotting
        plt.figure(figsize=(15, 10))
        
        # Price and indicators
        plt.subplot(3, 1, 1)
        plt.plot(data["Close"], label="Price", color="black")
        plt.plot(data["MA20"], label="MA20", color="blue", linestyle="--")
        plt.plot(data["MA50"], label="MA50", color="orange", linestyle="--")
        plt.plot(data["UpperBand"], label="Upper Band", color="red", alpha=0.3)
        plt.plot(data["LowerBand"], label="Lower Band", color="green", alpha=0.3)
        plt.fill_between(data.index, data["UpperBand"], data["LowerBand"], color="grey", alpha=0.1)
        
        # Mark trades
        for t in trade_log:
            if t[0] == "BUY":
                plt.scatter(t[1], t[2], marker="^", color="green", s=100)
            elif t[0] == "SELL":
                plt.scatter(t[1], t[2], marker="v", color="red", s=100)
        
        plt.title(f"{symbol} Price and Indicators")
        plt.legend()
        plt.grid()
        
        # RSI
        plt.subplot(3, 1, 2)
        plt.plot(data["RSI"], label="RSI", color="purple")
        plt.axhline(RSI_OVERBOUGHT, color="red", linestyle="--")
        plt.axhline(RSI_OVERSOLD, color="green", linestyle="--")
        plt.title("RSI")
        plt.grid()
        
        # MACD
        plt.subplot(3, 1, 3)
        plt.plot(data["MACD"], label="MACD", color="blue")
        plt.plot(data["MACD_Signal"], label="Signal", color="orange")
        plt.title("MACD")
        plt.grid()
        
        plt.tight_layout()
        plt.savefig(f"{symbol.replace('.', '-')}_plot.png")
        plt.close()

    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")
        send_telegram_message(f"❌ Error in processing {symbol}: {e}")
