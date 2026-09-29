import asyncio
import os
import re

from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, UserAlreadyParticipantError
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0") or 0)
API_HASH = os.getenv("TG_API_HASH", "")
SESSION = os.getenv("TG_SESSION", "")
NETWORK_ROOTS = [
    x.strip().lstrip("@") for x in os.getenv("SCANNER_NETWORK_ROOTS", "asasasalxk").split(",") if x.strip()
]
NETWORK_SAMPLE_MESSAGES = max(20, int(os.getenv("SCANNER_NETWORK_SAMPLE_MESSAGES", "100")))
NETWORK_MIN_AUTHORS = max(2, int(os.getenv("SCANNER_NETWORK_MIN_AUTHORS", "5")))
NETWORK_MAX_CHATS = max(5, int(os.getenv("SCANNER_NETWORK_MAX_CHATS", "40")))
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

    async def _group_activity(self, entity):
        """Return recent human-author activity without scraping participant lists."""
        authors = set()
        messages = 0
        async for msg in self.client.iter_messages(entity, limit=NETWORK_SAMPLE_MESSAGES):
            text = (getattr(msg, "raw_text", "") or "").strip()
            if not text:
                continue
            sender = await msg.get_sender()
            if not sender or getattr(sender, "bot", False):
                continue
            username = getattr(sender, "username", None)
            if not username:
                continue
            messages += 1
            authors.add(username.lower())
        return messages, len(authors)

    async def discover(self):
        """Discover only public discussion groups linked from the configured network roots."""
        if not await self._ensure_connected():
            raise RuntimeError(self.last_error or "Scanner не смог подключиться к Telegram.")

        candidates = {}
        link_re = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{5,})|@([A-Za-z0-9_]{5,})", re.I)

        for root in NETWORK_ROOTS:
            try:
                entity = await self.client.get_entity(root)
                texts = []
                try:
                    full = await self.client(functions.channels.GetFullChannelRequest(entity))
                    about = getattr(full.full_chat, "about", "") or ""
                    if about:
                        texts.append(about)
                except Exception:
                    pass

                async for msg in self.client.iter_messages(entity, limit=120):
                    text = (getattr(msg, "raw_text", "") or "").strip()
                    if text:
                        texts.append(text)

                # The root itself may also be a discussion group.
                root_username = getattr(entity, "username", None)
                if root_username:
                    candidates[root_username.lower()] = root_username

                for text in texts:
                    for match in link_re.finditer(text):
                        username = match.group(1) or match.group(2)
                        if username:
                            candidates[username.lower()] = username
            except FloodWaitError as e:
                self.last_error = f"Telegram FloodWait: {e.seconds}s"
                break
            except Exception as e:
                self.last_error = f"Сетка @{root}: {type(e).__name__}: {e}"

        found = []
        for username in list(candidates.values())[:NETWORK_MAX_CHATS * 3]:
            try:
                entity = await self.client.get_entity(username)
                if not getattr(entity, "megagroup", False):
                    continue
                public_username = getattr(entity, "username", None)
                if not public_username:
                    continue

                messages, unique_authors = await self._group_activity(entity)
                # Reject admin-only / nearly one-way groups. We want actual discussions.
                if unique_authors < NETWORK_MIN_AUTHORS:
                    continue

                found.append({
                    "tg_id": int(getattr(entity, "id", 0) or 0),
                    "username": public_username,
                    "title": getattr(entity, "title", public_username) or public_username,
                    "participants": int(getattr(entity, "participants_count", 0) or 0),
                    "query": f"network:{NETWORK_ROOTS[0] if NETWORK_ROOTS else 'root'}",
                    "recent_messages": messages,
                    "unique_authors": unique_authors,
                })
            except FloodWaitError as e:
                self.last_error = f"Telegram FloodWait: {e.seconds}s"
                break
            except Exception:
                continue

        found.sort(
            key=lambda x: (x["unique_authors"], x["recent_messages"], x["participants"]),
            reverse=True
        )
        rows = found[:NETWORK_MAX_CHATS]
        for item in rows:
            await self.db.upsert_scanner_source(
                item["tg_id"], item["username"], item["title"], "DISCOVERED",
                item["query"], item["participants"]
            )
        self.last_discovery_count = len(rows)
        if rows:
            self.last_error = ""
        return rows

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
