import requests
import json
import os


def load_config():
    try:
        # Try to load the JSON config file
        with open("config.json", "r") as config_file:
            print("Configuration loaded from JSON file.")
            return json.load(config_file)
    except FileNotFoundError:
        return {
            "TELEGRAM_TOKEN": os.getenv("telegram_token"),
            "CHAT_ID": os.getenv("chat_id")
        }

config = load_config()        

TELEGRAM_TOKEN = config["telegram_token"]
CHAT_ID = config["chat_id"]

# Send Message to Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
    payload = {"chat_id": config["chat_id"], "text": message}
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print(f"Telegram API Error: {response.json()}")
    return response.status_code == 200