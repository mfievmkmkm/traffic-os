import os
from datetime import datetime, timezone

from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "")
DISCOVERY_QUERIES = [
    x.strip() for x in os.getenv(
        "SCANNER_QUERIES",
        "crypto chat,крипто чат,trading chat,трейдинг чат,bitcoin chat,BTC chat,futures trading,фьючерсы"
    ).split(",") if x.strip()
]
MIN_SCORE = int(os.getenv("SCANNER_MIN_SCORE", "55"))
MAX_CONTEXT = int(os.getenv("SCANNER_CONTEXT_CHARS", "1200"))

class TelegramScanner:
    def __init__(self, db, score_func, offer_id):
        self.db = db
        self.score_func = score_func
        self.offer_id = offer_id
        self.client = None
        self.enabled = bool(API_ID and API_HASH and SESSION)
        self.last_error = ""

    async def start(self):
        if not self.enabled:
            return False
        self.client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
        await self.client.connect()
        if not await self.client.is_user_authorized():
            self.last_error = "TG_SESSION не авторизована"
            await self.client.disconnect()
            self.client = None
            return False
        self.client.add_event_handler(self._on_message, events.NewMessage)
        return True

    async def stop(self):
        if self.client:
            await self.client.disconnect()

    async def status(self):
        active = await self.db.scanner_sources("ACTIVE")
        discovered = await self.db.scanner_sources("DISCOVERED")
        return {
            "configured": self.enabled,
            "connected": bool(self.client and self.client.is_connected()),
            "active_sources": len(active),
            "discovered_sources": len(discovered),
            "last_error": self.last_error,
        }

    async def discover(self):
        if not self.client or not self.client.is_connected():
            raise RuntimeError("Scanner не подключён. Нужны TG_API_ID, TG_API_HASH и TG_SESSION.")
        found = {}
        for query in DISCOVERY_QUERIES:
            try:
                result = await self.client(functions.contacts.SearchRequest(q=query, limit=30))
            except FloodWaitError as e:
                self.last_error = f"Telegram FloodWait: {e.seconds}s"
                break
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                continue
            for chat in result.chats:
                username = getattr(chat, "username", None)
                # For lead discovery we need discussion groups, not broadcast-only channels.
                if not username or not getattr(chat, "megagroup", False):
                    continue
                tg_id = int(getattr(chat, "id", 0) or 0)
                if not tg_id:
                    continue
                title = getattr(chat, "title", username) or username
                participants = int(getattr(chat, "participants_count", 0) or 0)
                key = username.lower()
                prev = found.get(key)
                if not prev or participants > prev["participants"]:
                    found[key] = {
                        "tg_id": tg_id, "username": username, "title": title,
                        "participants": participants, "query": query,
                    }

        rows = sorted(found.values(), key=lambda x: x["participants"], reverse=True)
        for item in rows[:80]:
            await self.db.upsert_scanner_source(
                item["tg_id"], item["username"], item["title"], "DISCOVERED",
                item["query"], item["participants"]
            )
        return rows[:80]

    async def activate_source(self, source_id):
        if not self.client or not self.client.is_connected():
            raise RuntimeError("Scanner не подключён.")
        src = await self.db.get_scanner_source(source_id)
        if not src:
            raise ValueError("Источник не найден")
        entity = await self.client.get_entity(src["username"])
        try:
            await self.client(functions.channels.JoinChannelRequest(entity))
        except UserAlreadyParticipantError:
            pass
        except FloodWaitError as e:
            self.last_error = f"Telegram FloodWait: {e.seconds}s"
            raise RuntimeError(f"Telegram просит подождать {e.seconds} сек.")
        await self.db.set_scanner_source_status(source_id, "ACTIVE")
        return await self.db.get_scanner_source(source_id)

    async def pause_source(self, source_id):
        await self.db.set_scanner_source_status(source_id, "PAUSED")

    async def _on_message(self, event):
        try:
            if not event.is_group:
                return
            chat = await event.get_chat()
            username = getattr(chat, "username", None)
            if not username:
                return
            src = await self.db.scanner_source_by_username(username)
            if not src or src["status"] != "ACTIVE":
                return

            text = (event.raw_text or "").strip()
            if len(text) < 20:
                return
            await self.db.touch_scanner_source(src["id"])

            sender = await event.get_sender()
            if not sender or getattr(sender, "bot", False):
                return
            sender_username = getattr(sender, "username", None)
            if not sender_username:
                return

            score = self.score_func(text)
            if score < MIN_SCORE:
                return

            context = text[:MAX_CONTEXT]
            lead = await self.db.add_lead(
                sender_username,
                f"scanner:@{username}",
                context,
                score,
                self.offer_id,
            )
            await self.db.mark_scanner_lead(src["id"])
            await self.db.add_lead_evidence(
                lead["id"], src["id"], int(event.id), context, score
            )
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
