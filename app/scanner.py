import asyncio
import os

from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "")
DISCOVERY_QUERIES = [
    x.strip() for x in os.getenv(
        "SCANNER_QUERIES",
        "crypto chat,крипто чат,trading chat,трейдинг чат,bitcoin chat,BTC chat,futures trading,фьючерсы,криптовалюта,биткоин трейдинг,альткоины,спот трейдинг,crypto trading,bitcoin trading,altcoin trading,crypto market,bybit chat,binance chat,TON chat,solana chat"
    ).split(",") if x.strip()
]
MIN_SCORE = int(os.getenv("SCANNER_MIN_SCORE", "38"))
STRONG_SCORE = int(os.getenv("SCANNER_STRONG_SCORE", "72"))
MAX_CONTEXT = int(os.getenv("SCANNER_CONTEXT_CHARS", "1200"))
DISCOVERY_HOURS = max(1, int(os.getenv("SCANNER_DISCOVERY_HOURS", "3")))
HEALTH_HOURS = max(1, int(os.getenv("SCANNER_HEALTH_HOURS", "12")))
AUTO_PAUSE_MESSAGES = max(0, int(os.getenv("SCANNER_AUTO_PAUSE_MESSAGES", "2000")))
AUTO_PAUSE_MAX_LEADS = max(0, int(os.getenv("SCANNER_AUTO_PAUSE_MAX_LEADS", "0")))


class TelegramScanner:
    def __init__(self, db, score_func, offer_id, strong_lead_callback=None):
        self.db = db
        self.score_func = score_func
        self.offer_id = offer_id
        self.strong_lead_callback = strong_lead_callback
        self.client = None
        self.enabled = bool(API_ID and API_HASH and SESSION)
        self.last_error = ""
        self.last_discovery_count = 0
        self.auto_paused_count = 0

    async def _ensure_connected(self):
        """Keep the MTProto client alive across Railway/network reconnects."""
        if not self.enabled:
            missing = []
            if not API_ID: missing.append("TG_API_ID")
            if not API_HASH: missing.append("TG_API_HASH")
            if not SESSION: missing.append("TG_SESSION")
            self.last_error = "Не заданы Railway Variables: " + ", ".join(missing)
            return False

        try:
            if self.client is None:
                self.client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
                self.client.add_event_handler(self._on_message, events.NewMessage)

            if not self.client.is_connected():
                await self.client.connect()

            if not await self.client.is_user_authorized():
                self.last_error = "TG_SESSION существует, но Telegram-сессия больше не авторизована"
                return False

            self.last_error = ""
            return True
        except Exception as e:
            self.last_error = f"Telegram reconnect {type(e).__name__}: {e}"
            return False

    async def start(self):
        return await self._ensure_connected()

    async def stop(self):
        if self.client:
            await self.client.disconnect()

    async def status(self):
        if self.enabled and (not self.client or not self.client.is_connected()):
            await self._ensure_connected()
        active = await self.db.scanner_sources("ACTIVE")
        discovered = await self.db.scanner_sources("DISCOVERED")
        return {
            "configured": self.enabled,
            "connected": bool(self.client and self.client.is_connected()),
            "active_sources": len(active),
            "discovered_sources": len(discovered),
            "last_discovery_count": self.last_discovery_count,
            "auto_paused_count": self.auto_paused_count,
            "last_error": self.last_error,
        }

    async def discover(self):
        if not await self._ensure_connected():
            raise RuntimeError(self.last_error or "Scanner не смог подключиться к Telegram.")
        found = {}
        for query in DISCOVERY_QUERIES:
            try:
                result = await self.client(functions.contacts.SearchRequest(q=query, limit=40))
            except FloodWaitError as e:
                self.last_error = f"Telegram FloodWait: {e.seconds}s"
                break
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                continue
            for chat in result.chats:
                username = getattr(chat, "username", None)
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
                        "tg_id": tg_id,
                        "username": username,
                        "title": title,
                        "participants": participants,
                        "query": query,
                    }

        rows = sorted(found.values(), key=lambda x: x["participants"], reverse=True)
        for item in rows[:150]:
            await self.db.upsert_scanner_source(
                item["tg_id"], item["username"], item["title"], "DISCOVERED",
                item["query"], item["participants"]
            )
        self.last_discovery_count = len(rows[:150])
        if rows:
            self.last_error = ""
        return rows[:150]

    async def activate_source(self, source_id):
        if not await self._ensure_connected():
            raise RuntimeError(self.last_error or "Scanner не смог подключиться к Telegram.")
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

    async def maintenance_loop(self):
        """Background discovery + conservative source health checks."""
        if not self.enabled:
            return
        discovery_seconds = DISCOVERY_HOURS * 3600
        health_seconds = HEALTH_HOURS * 3600
        last_discovery = 0.0
        last_health = 0.0
        loop = asyncio.get_running_loop()

        while True:
            now = loop.time()
            try:
                if not await self._ensure_connected():
                    await asyncio.sleep(60)
                    continue
                if now - last_discovery >= discovery_seconds:
                    await self.discover()
                    last_discovery = now
                if now - last_health >= health_seconds:
                    if AUTO_PAUSE_MESSAGES > 0:
                        paused = await self.db.auto_pause_scanner_sources(
                            AUTO_PAUSE_MESSAGES, AUTO_PAUSE_MAX_LEADS
                        )
                        self.auto_paused_count += len(paused)
                    last_health = now
            except FloodWaitError as e:
                self.last_error = f"Telegram FloodWait: {e.seconds}s"
            except Exception as e:
                self.last_error = f"maintenance {type(e).__name__}: {e}"
            await asyncio.sleep(300)

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
            inserted = await self.db.add_lead_evidence(
                lead["id"], src["id"], int(event.id), context, score
            )
            if not inserted:
                return

            await self.db.mark_scanner_lead(src["id"])
            if score >= STRONG_SCORE and self.strong_lead_callback:
                key = f"strong_lead:{src['id']}:{event.id}"
                if not await self.db.get_state(key):
                    await self.strong_lead_callback(lead, src, context, score)
                    await self.db.set_state(key, "1")
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
