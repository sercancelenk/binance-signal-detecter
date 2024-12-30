import requests
import pandas as pd
import json
import time
from datetime import datetime
from cachetools import TTLCache
from telegram_bot import send_telegram_message
import talib
import numpy as np  # Import NumPy
import threading

pd.set_option('future.no_silent_downcasting', True)

# Load Config
with open("config.json", "r") as config_file:
    config = json.load(config_file)

# Constants
BINANCE_FUTURES_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
BINANCE_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BINANCE_HISTORICAL_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_API_KEY = config["binance_api_key"]
PRICE_CHANGE_THRESHOLD = config["price_change_threshold"]
VOLUME_CHANGE_THRESHOLD = config["volume_change_threshold"]
BATCH_INTERVAL = config["batch_interval"]

# Global Variables
detected_signals = []  # Store all detected signals for API use
usdt_pairs_cache = None  # Cache USDT pairs to prevent re-fetching
lock = threading.Lock()  # Thread lock to prevent duplicate runs

# Fetch Binance Futures USDT Pairs
def fetch_binance_futures_usdt_pairs():
    global usdt_pairs_cache
    if usdt_pairs_cache is not None:  # Return cached result if available
        return usdt_pairs_cache

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    try:
        response = requests.get(BINANCE_FUTURES_INFO_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        usdt_pairs_cache = [
            symbol_info['symbol'] for symbol_info in data['symbols']
            if symbol_info['quoteAsset'] == 'USDT'
        ]
        print(f"Fetched {len(usdt_pairs_cache)} USDT pairs from Binance.")
        return usdt_pairs_cache
    except Exception as e:
        print(f"Error fetching Binance Futures USDT pairs: {e}")
        return []

# Fetch Binance Data for USDT Pairs
def fetch_binance_data(usdt_pairs):
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    try:
        response = requests.get(BINANCE_TICKER_URL, headers=headers)
        response.raise_for_status()
        data = pd.DataFrame(response.json())
        data = data[data['symbol'].isin(usdt_pairs)]
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
        data = data.dropna(subset=["volume"])
        print(f"Fetched {len(data)} rows of Binance data.")
        return data
    except Exception as e:
        print(f"Error fetching Binance Futures data: {e}")
        return pd.DataFrame()

# Fetch Historical Close Prices for a Symbol
def fetch_historical_close_prices(symbol, interval='1h', limit=50):
    url = BINANCE_HISTORICAL_KLINES_URL
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        close_prices = [float(candle[4]) for candle in data]  # 4th index is close price
        return close_prices
    except Exception as e:
        print(f"Error fetching historical prices for {symbol}: {e}")
        return []

# Calculate Market Sentiment
def calculate_market_sentiment(symbol, market_data, average_volume):
    try:
        close_prices = np.array(market_data.get("close_prices", []))
        if len(close_prices) < 14:
            print(f"Insufficient historical data for {symbol}")
            return calculate_market_sentiment_by_volume(symbol, market_data, average_volume)

        current_volume = market_data["volume"]
        volume_spike = (current_volume - average_volume) / average_volume
        volume_sentiment = max(0, min(1, (volume_spike + 1) / 2))

        rsi = talib.RSI(close_prices, timeperiod=14)
        stoch_rsi = 100 * ((rsi - rsi.min()) / (rsi.max() - rsi.min()))
        stock_rsi_sentiment = 1 if stoch_rsi[-1] < 20 else 0 if stoch_rsi[-1] > 80 else 0.5

        macd, macd_signal, _ = talib.MACD(close_prices, fastperiod=12, slowperiod=26, signalperiod=9)
        macd_sentiment = 1 if macd[-1] > macd_signal[-1] else 0

        rsi_sentiment = 1 if rsi[-1] < 30 else 0 if rsi[-1] > 70 else 0.5

        price_change_percent = market_data["price_change_percent"]
        price_sentiment = max(0, min(1, price_change_percent / 100))

        market_sentiment = (
            0.4 * volume_sentiment +
            0.2 * stock_rsi_sentiment +
            0.2 * macd_sentiment +
            0.2 * rsi_sentiment
        )
        return market_sentiment
    except Exception as e:
        print(f"Error calculating market sentiment for {symbol}: {e}")
        return None

def calculate_market_sentiment_by_volume(symbol, market_data, average_volume):
    try:
        current_volume = market_data["volume"]
        price_change_percent = market_data["price_change_percent"]
        volume_spike = (current_volume - average_volume) / average_volume
        volume_sentiment = max(0, min(1, (volume_spike + 1) / 2))
        price_sentiment = max(0, min(1, price_change_percent / 100))
        confidence_boost = 0.1 if volume_spike > 2 else 0
        return min(0.7 * volume_sentiment + 0.3 * price_sentiment + confidence_boost, 1)
    except Exception as e:
        print(f"Error calculating market sentiment for {symbol}: {e}")
        return None

# Detect Pumps
def detect_pumps():
    global detected_signals
    with lock:  # Ensure only one thread runs detect_pumps
        usdt_pairs = fetch_binance_futures_usdt_pairs()
        data = fetch_binance_data(usdt_pairs)

        if data.empty:
            print("No data fetched from Binance. Skipping detection.")
            return

        average_volume = data["volume"].mean()
        batch_signals = []

        for _, row in data.iterrows():
            symbol = row["symbol"]
            price_change = float(row["priceChangePercent"])
            volume = float(row["volume"])
            close_prices = fetch_historical_close_prices(symbol, interval='1h', limit=50)

            market_data = {
                "volume": volume,
                "price_change_percent": price_change,
                "close_prices": close_prices
            }

            market_sentiment = calculate_market_sentiment(symbol, market_data, average_volume)
            if market_sentiment and market_sentiment > 0.79 and (price_change > -2 and price_change < 1):
                signal = {
                    "symbol": symbol,
                    "priceChangePercent": price_change,
                    "volume": volume,
                    "sentiment_score": market_sentiment,
                    "action": "BUY",
                    "timestamp": datetime.now().isoformat(),
                }
                batch_signals.append(signal)
                detected_signals.append(signal)

        if batch_signals:
            send_batch_to_telegram(batch_signals)

# Send Batch Signals to Telegram
def send_batch_to_telegram(signals):
    if not signals:
        return

    message = "🚀 Pump Signals Detected:\n\n"
    for signal in signals:
        message += (
            f"🔸 Symbol: {signal['symbol']}\n"
            f"📈 Price Change: {signal['priceChangePercent']}%\n"
            f"📊 Volume: {signal['volume']}\n"
            f"🗣 Sentiment Score: {signal['sentiment_score']:.2f}\n"
            f"📍 Action: {signal['action']}\n"
            f"🕒 Time: {signal['timestamp']}\n\n"
        )
    send_telegram_message(message)

# Batch Processor
def batch_processor():
    while True:
        print(f"Running pump detection at {datetime.now()}")
        detect_pumps()
        time.sleep(BATCH_INTERVAL)