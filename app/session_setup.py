import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

def main():
    api_id = int(os.getenv("TG_API_ID", "0") or input("TG_API_ID: ").strip())
    api_hash = os.getenv("TG_API_HASH", "") or input("TG_API_HASH: ").strip()
    print("Telegram пришлёт код входа. Он вводится только здесь и никуда не отправляется.")
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\nTG_SESSION (храни как пароль, добавь только в Railway Variables):\n")
        print(client.session.save())

if __name__ == "__main__":
    main()
