import os
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from joblib import dump, load
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Config
SYMBOLS = ["HUT.TO", "SHOP.TO"]
INTERVAL = "15m"
PERIOD = "7d"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Technical Indicators
def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    rs = gain.rolling(window).mean() / loss.rolling(window).mean()
    return 100 - (100 / (1 + rs))

def calculate_indicators(df):
    df['MA20'] = df['Close'].rolling(20).mean()
    df['RSI'] = calculate_rsi(df)
    df['5min_return'] = df['Close'].pct_change(1)
    df['volatility'] = df['Close'].rolling(20).std()
    df['volume_spike'] = df['Volume'] / df['Volume'].rolling(20).mean()
    df['target'] = np.where(df['Close'].shift(-1) > df['Close'], 1, 0)
    return df.dropna()

# ML Model
def train_model(data):
    features = ['MA20', 'RSI', '5min_return', 'volatility', 'volume_spike']
    X = data[features]
    y = data['target']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(X_train, y_train)
    
    print(f"Model Accuracy: {model.score(X_test, y_test):.2%}")
    dump(model, 'model.joblib')
    return model

# Trading Logic
def generate_signal(row, model):
    features = ['MA20', 'RSI', '5min_return', 'volatility', 'volume_spike']
    ml_input = [row[features].values]
    proba = model.predict_proba(ml_input)[0][1]
    
    if proba > 0.7 and row['Close'] > row['MA20']:
        return "BUY"
    elif proba < 0.3:
        return "SELL"
    return None

def send_alert(symbol, signal, price):
    if TELEGRAM_TOKEN:
        message = f"🚨 {symbol} {signal} at ${price:.2f}"
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )

# Main Execution
def run_bot():
    for symbol in SYMBOLS:
        data = yf.download(symbol, period=PERIOD, interval=INTERVAL)
        data = calculate_indicators(data)
        
        try:
            model = load('model.joblib')  # Load existing model
        except:
            model = train_model(data.copy())
        
        latest = data.iloc[-1]
        signal = generate_signal(latest, model)
        
        if signal:
            send_alert(symbol, signal, latest['Close'])
            plot_data(data, symbol)

def plot_data(data, symbol):
    plt.figure(figsize=(10,5))
    plt.plot(data['Close'], label='Price')
    plt.plot(data['MA20'], label='MA20')
    plt.title(f"{symbol} Price Analysis")
    plt.legend()
    plt.savefig(f"{symbol}_analysis.png")
    plt.close()

if __name__ == "__main__":
    run_bot()