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
import os

pd.set_option('future.no_silent_downcasting', True)

# Load Config    
def load_config():
    """
    Load configuration from a JSON file or environment variables.

    Priority:
    1. Read configuration from "config.json".
    2. If the file is not found, read from environment variables.

    Returns:
        dict: Configuration values (API key, thresholds, intervals, etc.).
    """
    try:
        with open("config.json", "r") as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        return {
            "BINANCE_API_KEY": os.getenv("binance_api_key"),
            "PRICE_CHANGE_THRESHOLD": float(os.getenv("price_change_threshold", 5.0)),
            "VOLUME_CHANGE_THRESHOLD": float(os.getenv("volume_change_threshold", 1000)),
            "BATCH_INTERVAL": int(os.getenv("batch_interval", 300)),
        }

config = load_config()

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

def fetch_binance_futures_usdt_pairs():
    """
    Fetch all USDT trading pairs available on Binance Futures.

    Uses caching to prevent redundant API calls if pairs are already fetched.

    Returns:
        list: List of USDT trading pairs (e.g., ['BTCUSDT', 'ETHUSDT']).
    """
    global usdt_pairs_cache
    if usdt_pairs_cache is not None:
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

def fetch_binance_data(usdt_pairs):
    """
    Fetch real-time trading data for USDT pairs from Binance.

    Filters data to include only specified USDT pairs.

    Args:
        usdt_pairs (list): List of USDT trading pairs.

    Returns:
        pd.DataFrame: DataFrame containing trading data (symbol, volume, price change, etc.).
    """
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

def fetch_historical_close_prices(symbol, interval='1h', limit=50):
    """
    Fetch historical close prices for a specific symbol.

    Args:
        symbol (str): The trading pair (e.g., 'BTCUSDT').
        interval (str): Time interval for candlesticks (e.g., '1h', '1d').
        limit (int): Number of candlesticks to fetch.

    Returns:
        list: List of close prices.
    """
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

def calculate_market_sentiment_by_volume(symbol, market_data, average_volume, weights=None):
    """
    Calculate market sentiment for a trading pair based on volume and price changes.

    Sentiment is weighted and normalized, with optional confidence boosts.
    Algorithm:
    1. **Volume Sentiment**:
        - Calculate volume spike: `(current_volume - average_volume) / average_volume`.
        - Normalize to range [0, 1].
    2. **Price Sentiment**:
        - Normalize price change percentage to range [0, 1].
    3. **Confidence Boost**:
        - Add a small boost for high volume spikes or extreme price changes.
    4. **Weighted Sentiment**:
        - Combine volume and price sentiments using predefined weights.

    Args:
        symbol (str): The trading pair symbol.
        market_data (dict): Contains 'volume' and 'price_change_percent'.
        average_volume (float): Average trading volume for normalization.
        weights (dict): Optional weights for 'volume' and 'price'.

    Returns:
        float: Normalized sentiment score (0 to 1), or None if an error occurs.
    """
    if weights is None:
        weights = {"volume": 0.7, "price": 0.3}

    try:
        current_volume = market_data["volume"]
        price_change_percent = market_data["price_change_percent"]

        # Volume Sentiment
        volume_spike = (current_volume - average_volume) / average_volume
        volume_sentiment = normalize_value(volume_spike + 1, 0, 2)

        # Price Sentiment
        price_sentiment = normalize_value(price_change_percent, 0, 100)

        # Confidence Boost
        confidence_boost = calculate_confidence_boost(volume_spike, price_change_percent)

        # Weighted Sentiment Score
        market_sentiment = (
            weights["volume"] * volume_sentiment +
            weights["price"] * price_sentiment +
            confidence_boost
        )
        return min(market_sentiment, 1)
    except KeyError as e:
        print(f"[{symbol}] Missing required market data: {e}")
    except Exception as e:
        print(f"[{symbol}] Error calculating market sentiment: {e}")
    return None

def normalize_value(value, min_value, max_value):
    """
    Normalize a value to a range of 0 to 1.

    Args:
        value (float): The value to normalize.
        min_value (float): Minimum possible value.
        max_value (float): Maximum possible value.

    Returns:
        float: Normalized value between 0 and 1.
    """
    try:
        return max(0, min(1, (value - min_value) / (max_value - min_value)))
    except ZeroDivisionError:
        return 0.5  # Neutral score if range is invalid

def calculate_confidence_boost(volume_spike, price_change_percent):
    """
    Calculate a confidence boost based on significant volume or price changes.

    Args:
        volume_spike (float): Ratio of current volume to average volume.
        price_change_percent (float): Percentage change in price.

    Returns:
        float: Confidence boost (0 to 0.2).
    """
    volume_boost = 0.1 if volume_spike > 2 else 0
    price_boost = 0.1 if abs(price_change_percent) > 10 else 0
    return min(volume_boost + price_boost, 0.2)

def detect_pumps():
    message = "🚀 Signal Detection started.."
    send_telegram_message(message)
    
    """
    Detect potential pump signals for USDT trading pairs.

    Combines market sentiment analysis and volume-based metrics to identify buy opportunities.
    Sends detected signals in batches to Telegram.
    """
    global detected_signals
    with lock:
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

            market_sentiment = calculate_market_sentiment_by_volume(symbol, market_data, average_volume)
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

def send_batch_to_telegram(signals):
    """
    Send detected pump signals as a batch to Telegram.

    Args:
        signals (list): List of detected signals.
    """
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

def batch_processor():
    """
    Continuously run the pump detection algorithm at regular intervals.

    Logs the timestamp and runs the detection process.
    """
    while True:
        print(f"Running pump detection at {datetime.now()}")
        detect_pumps()
        time.sleep(BATCH_INTERVAL)