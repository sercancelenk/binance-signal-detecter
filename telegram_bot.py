import requests
import json

# Load Config
with open("config.json", "r") as config_file:
    config = json.load(config_file)

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