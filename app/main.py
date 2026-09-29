import os, asyncio, csv, io, html
from datetime import datetime
from zoneinfo import ZoneInfo

import uvicorn
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from .db import DB
from .ai import reply_suggestion, outreach_hooks
from .web import create_app
from .scanner import TelegramScanner

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN','')
DBURL = os.getenv('DATABASE_URL','')
RATE = float(os.getenv('DEFAULT_RATE','0.70'))
REF = os.getenv('REFERRAL_LINK','')
OFFER = os.getenv('DEFAULT_OFFER','Crypto Traffic')
ADMINS = {int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
PORT = int(os.getenv('PORT','8080'))
TZ_NAME = os.getenv('REPORT_TIMEZONE','Asia/Yekaterinburg')
REPORT_HOUR = int(os.getenv('DAILY_REPORT_HOUR','21'))
DASH_TOKEN = os.getenv('DASHBOARD_TOKEN','')
PUBLIC_URL = os.getenv('PUBLIC_URL','').rstrip('/')

db = DB(DBURL)
dp = Dispatcher()
DEFAULT_OFFER_ID = None
scanner = None

def allowed(uid): return bool(ADMINS) and uid in ADMINS

class AdminCallbackMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not event.from_user or not allowed(event.from_user.id):
            try:
                await event.answer('Нет доступа', show_alert=True)
            except Exception:
                pass
            return None
        return await handler(event, data)

dp.callback_query.outer_middleware(AdminCallbackMiddleware())

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎯 В работу',callback_data='next'),InlineKeyboardButton(text='🔎 Lead Finder',callback_data='finder')],
        [InlineKeyboardButton(text='➕ Новый лид',callback_data='help_add'),InlineKeyboardButton(text='🧲 Зацепить',callback_data='hook_help')],
        [InlineKeyboardButton(text='✨ Помощник ответа',callback_data='aihelp'),InlineKeyboardButton(text='⏰ На сегодня',callback_data='followups')],
        [InlineKeyboardButton(text='📊 Результаты',callback_data='stats'),InlineKeyboardButton(text='🧭 Источники',callback_data='sources')],
        [InlineKeyboardButton(text='🧪 A/B',callback_data='ab'),InlineKeyboardButton(text='💼 Офферы',callback_data='offers')],
        [InlineKeyboardButton(text='📤 Экспорт',callback_data='export'),InlineKeyboardButton(text='💰 Выплаты',callback_data='money')],
        [InlineKeyboardButton(text='🖥 Панель',callback_data='dashboard'),InlineKeyboardButton(text='📋 Отчёт',callback_data='report')],
    ])

def kb(lid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🧲 AI-заход',callback_data=f'hook:{lid}'),InlineKeyboardButton(text='💬 Текст A/B',callback_data=f't:A:{lid}')],
        [InlineKeyboardButton(text='✅ Написал',callback_data=f's:CONTACTED:{lid}'),InlineKeyboardButton(text='🚫 Пропустить',callback_data=f's:SKIPPED:{lid}')],
        [InlineKeyboardButton(text='↩️ Ответил',callback_data=f's:REPLIED:{lid}'),InlineKeyboardButton(text='🟢 Интерес',callback_data=f's:INTERESTED:{lid}')],
        [InlineKeyboardButton(text='🔗 Ссылка',callback_data=f'link:{lid}'),InlineKeyboardButton(text='👤 Подписался',callback_data=f's:JOINED:{lid}')],
        [InlineKeyboardButton(text='💵 Засчитан',callback_data=f's:APPROVED:{lid}'),InlineKeyboardButton(text='🔴 Не интересно',callback_data=f's:NOT_INTERESTED:{lid}')],
        [InlineKeyboardButton(text='⏰ Follow-up 24ч',callback_data=f'f:24:{lid}')],
    ])

def script(l, variant):
    ctx=(l['context'] or '').lower(); topic='крипте/трейду'
    if 'фьюч' in ctx: topic='фьючам'
    elif 'битко' in ctx or 'btc' in ctx: topic='биткоину и рынку'
    if variant=='A':
        return f'привет, увидел тебя в тематическом чате по {topic}. есть небольшое комьюнити по рынку — по твоим сообщениям подумал, что может быть интересно. если хочешь, кину посмотреть'
    return f'привет. видел твои сообщения про {topic}. наткнулся на канал по рынку и трейду, показалось релевантным. если актуально — могу скинуть ссылку'

def score_ctx(ctx):
    """Topical relevance only; never scores protected/sensitive traits."""
    x=(ctx or '').lower()
    s=8
    signals=[
        ('фьюч',24),('futures',24),('трейд',22),('trading',22),
        ('btc',18),('битко',18),('eth',15),('эфир',15),
        ('крипт',16),('рынок',10),('лонг',12),('шорт',12),
        ('позици',10),('бирж',10),('спот',12),('альт',10),
        ('ликвид',8),('плеч',10),('график',8),('теханализ',12),
        ('торг',18),('сделк',14),('вход',10),('стоп',10),('тейк',10),
        ('уров',8),('пробой',10),('скальп',16),('интрадей',16),
        ('bybit',10),('binance',10),('solana',10),(' sol ',10),('ton ',10),
        ('мемкоин',8),('memecoin',8),('pump',8),('памп',8),('коррекц',8)
    ]
    for k,n in signals:
        if k in x: s += n
    low_value=['реферал', 'накрут', 'взаимн', 'боты купить', 'спам']
    for k in low_value:
        if k in x: s -= 20
    return max(0,min(s,100))

def contextual_hooks(l):
    """Non-AI hooks for Telegram Scanner leads; uses only broad topical signals."""
    x=(l['context'] or '').lower()
    if 'фьюч' in x or 'futures' in x or 'плеч' in x:
        topic='фьючерсам'
        q='ты сейчас больше BTC смотришь или альты?'
    elif 'btc' in x or 'битко' in x:
        topic='битку'
        q='ты сейчас больше внутри дня смотришь или среднесрок?'
    elif 'eth' in x or 'эфир' in x:
        topic='эфиру'
        q='ты сейчас ETH отдельно торгуешь или вместе с BTC смотришь?'
    elif 'спот' in x:
        topic='споту'
        q='ты сейчас больше набор позиций смотришь или уже сидишь в рынке?'
    else:
        topic='рынку'
        q='ты сейчас больше трейдишь или просто рынок отслеживаешь?'
    return [
        f'привет. увидел твой комментарий по {topic} — {q}',
        f'привет, заметил тебя в обсуждении по {topic}. есть небольшое тематическое комьюнити без общего криптошума. если актуально — могу скинуть посмотреть',
        f'привет. по твоему сообщению понял, что тема {topic} тебе актуальна. могу скинуть один профильный канал, если хочешь',
    ]

async def report_text(days=None):
    s=await db.stats(RATE,days); con=s['contacted'] or 1; label=f'за {days} дн.' if days else 'всего'
    return (f"📊 <b>TRAFFIC OS · {label}</b>\n\nЛидов: {s['total']} · NEW: {s['new']}\nКонтактов: {s['contacted']}\nОтветили: {s['replied']}\nИнтерес: {s['interested']}\n"
            f"Ссылка: {s['link_sent']}\nПодписались: {s['joined']}\nЗасчитано: {s['approved']}\n\nContact → Approved: {s['approved']/con*100:.1f}%\n"
            f"💰 Начислено: ${float(s['revenue']):.2f}\n💳 Оплачено: ${float(s['paid_value']):.2f}\n⏳ Ожидается: ${float(s['revenue']-s['paid_value']):.2f}")

async def show_next(m):
    l=await db.next_lead()
    if not l: return await m.answer('Очередь NEW пуста.\n/add @user | источник | контекст',reply_markup=menu())
    evidence=await db.lead_evidence(l['id'],1)
    ev=''
    if evidence:
        e=evidence[0]
        ev=f"\n\n🔎 <b>Почему попал:</b> @{html.escape(e['source_username'] or 'source')} · message #{e['message_id']}"
    await m.answer(
        f"🎯 <b>LEAD #{l['id']}</b>\n\n👤 @{html.escape(l['username'])}\n📍 {html.escape(l['source'])}\n"
        f"⭐ {l['score']}/100\n💼 {html.escape(l['offer_name'] or 'default')}\n🏷 {html.escape(l['campaign_name'] or '—')}\n\n"
        f"🧠 {html.escape(l['context'] or '—')}{ev}",
        reply_markup=kb(l['id'])
    )

@dp.message(CommandStart())
async def start(m:Message):
    if allowed(m.from_user.id): await m.answer('⚡ <b>TRAFFIC OS V5</b>\nCRM · AI · Dashboard · отчёты · аналитика',reply_markup=menu())

@dp.message(Command('add'))
async def add(m:Message):
    if not allowed(m.from_user.id): return
    p=[x.strip() for x in (m.text or '').partition(' ')[2].split('|')]
    if not p[0]: return await m.answer('/add @username | источник | контекст')
    ctx=p[2] if len(p)>2 else ''
    l=await db.add_lead(p[0],p[1] if len(p)>1 else 'manual',ctx,score_ctx(ctx),DEFAULT_OFFER_ID)
    await m.answer(f"✅ @{l['username']} · score {l['score']} · {l['status']}",reply_markup=menu())

@dp.message(Command('import'))
async def imp(m:Message):
    if not allowed(m.from_user.id): return
    raw=(m.text or '').partition('\n')[2]
    if not raw: return await m.answer('Формат:\n<code>/import\n@user1 | Crypto Chat | обсуждает BTC\n@user2 | Futures | фьючерсы</code>')
    n=0
    for line in raw.splitlines():
        p=[x.strip() for x in line.split('|')]
        if p and p[0]:
            ctx=p[2] if len(p)>2 else ''
            await db.add_lead(p[0],p[1] if len(p)>1 else 'import',ctx,score_ctx(ctx),DEFAULT_OFFER_ID); n+=1
    await m.answer(f'✅ Обработано строк: {n}',reply_markup=menu())

@dp.message(Command('find'))
async def find_cmd(m:Message):
    if not allowed(m.from_user.id): return
    raw=(m.text or '').partition('\n')[2]
    if not raw:
        return await m.answer(
            '🔎 <b>Lead Finder</b>\n\n'
            'Пришли кандидатов пачкой:\n'
            '<code>/find\n@user1 | Crypto Chat | обсуждает BTC и фьючерсы\n'
            '@user2 | Market Chat | спрашивает про ETH</code>\n\n'
            'Я уберу дубли, оценю релевантность и добавлю сильных в очередь.'
        )
    added=[]; skipped=[]
    for line in raw.splitlines()[:100]:
        p=[x.strip() for x in line.split('|',2)]
        if not p or not p[0]: continue
        ctx=p[2] if len(p)>2 else ''
        sc=score_ctx(ctx)
        if sc < 35:
            skipped.append(p[0])
            continue
        l=await db.add_lead(p[0],p[1] if len(p)>1 else 'finder-import',ctx,sc,DEFAULT_OFFER_ID)
        added.append((l['username'],l['score']))
    added.sort(key=lambda x:x[1],reverse=True)
    top='\n'.join(f'⭐ {sc}/100 · @{u}' for u,sc in added[:15]) or '—'
    await m.answer(
        f'🔎 <b>LEAD FINDER · ГОТОВО</b>\n\n'
        f'В очередь: <b>{len(added)}</b>\n'
        f'Слабых пропущено: <b>{len(skipped)}</b>\n\n'
        f'<b>Лучшие:</b>\n{top}\n\n'
        'Жми 🎯 «В работу» — лучшие идут первыми.',
        reply_markup=menu()
    )

@dp.message(Command('hook'))
async def hook_cmd(m:Message):
    if not allowed(m.from_user.id): return
    raw=(m.text or '').partition(' ')[2].strip()
    if not raw.isdigit():
        return await m.answer('🧲 Формат: <code>/hook LEAD_ID</code>')
    l=await db.get(int(raw))
    if not l: return await m.answer('Лид не найден.')
    if (l['source'] or '').startswith('scanner:'):
        hooks='\n'.join(f'{chr(65+i)}) {x}' for i,x in enumerate(contextual_hooks(l)))
    else:
        hooks=await outreach_hooks(l['context'],l['source'])
    await m.answer(
        f'🧲 <b>3 захода для @{html.escape(l["username"])}</b>\n\n'
        f'{html.escape(hooks)}\n\n'
        'Выбери тот, который соответствует реальному контексту. Ссылку сразу не отправляй.'
    )

@dp.message(Command('offer'))
async def offer(m:Message):
    if not allowed(m.from_user.id): return
    p=[x.strip() for x in (m.text or '').partition(' ')[2].split('|')]
    if len(p)<2: return await m.answer('/offer Название | 0.70 | https://ref-link')
    try: r=float(p[1])
    except ValueError: return await m.answer('Ставка должна быть числом.')
    o=await db.add_offer(p[0],r,p[2] if len(p)>2 else '')
    await m.answer(f"✅ Оффер #{o['id']}: {o['name']} · ${float(o['rate']):.2f}")

@dp.message(Command('campaign'))
async def campaign(m:Message):
    if not allowed(m.from_user.id): return
    p=[x.strip() for x in (m.text or '').partition(' ')[2].split('|')]
    if len(p)<2 or not p[1].isdigit(): return await m.answer('/campaign Название | OFFER_ID')
    c=await db.add_campaign(p[0],int(p[1])); await m.answer(f"✅ Кампания #{c['id']}: {c['name']}")

@dp.message(Command('ai'))
async def ai_cmd(m:Message):
    if not allowed(m.from_user.id): return
    p=(m.text or '').partition(' ')[2].strip(); bits=p.split('|',1)
    if len(bits)<2 or not bits[0].strip().isdigit(): return await m.answer('/ai LEAD_ID | сообщение человека')
    lid=int(bits[0]); l=await db.get(lid)
    if not l: return await m.answer('Лид не найден.')
    ans=await reply_suggestion(l['context'],bits[1].strip()); await db.save_dialogue(lid,bits[1].strip(),ans)
    await m.answer(f'🤖 <b>Ответы для @{l["username"]}</b>\n\n{ans}')

@dp.message(Command('report'))
async def report_cmd(m:Message):
    if allowed(m.from_user.id): await m.answer(await report_text(1),reply_markup=menu())

def scanner_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔭 Найти крипто-чаты',callback_data='scan:discover')],
        [InlineKeyboardButton(text='➕ Подключить 3 лучших',callback_data='scan:activate3')],
        [InlineKeyboardButton(text='📡 Подключённые',callback_data='scan:active'),
         InlineKeyboardButton(text='🗂 Найденные',callback_data='scan:found')],
        [InlineKeyboardButton(text='🏆 Эффективность источников',callback_data='scan:performance')],
        [InlineKeyboardButton(text='🎯 К лидам',callback_data='next')],
    ])

def source_rows(rows, mode='found'):
    buttons=[]
    for r in rows[:20]:
        title=(r['title'] or r['username'])[:28]
        if mode=='active':
            buttons.append([InlineKeyboardButton(
                text=f"⏸ {title} · {r['leads_found']} лид.",
                callback_data=f"src:pause:{r['id']}"
            )])
        else:
            size=f"{r['participants']//1000}k" if r['participants']>=1000 else str(r['participants'] or '—')
            buttons.append([InlineKeyboardButton(
                text=f"➕ {title} · {size}",
                callback_data=f"src:on:{r['id']}"
            )])
    buttons.append([InlineKeyboardButton(text='⬅️ Scanner',callback_data='finder')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(F.data=='finder')
async def finder_cb(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    st=await scanner.status() if scanner else {'configured':False,'connected':False,'active_sources':0,'discovered_sources':0,'last_error':''}
    icon='🟢' if st['connected'] else '🟠'
    setup='' if st['configured'] else '\n\n⚙️ Для автосканера добавь TG_API_ID, TG_API_HASH и TG_SESSION в Railway.'
    err=f"\n⚠️ {html.escape(st['last_error'])}" if st.get('last_error') else ''
    await c.message.answer(
        f"🔎 <b>TRAFFIC SCANNER</b>\n\n{icon} Telegram Scanner: {'онлайн' if st['connected'] else 'не подключён'}\n"
        f"📡 Активных источников: <b>{st['active_sources']}</b>\n"
        f"🗂 Найдено кандидатов: <b>{st['discovered_sources']}</b>\n"
        f"🔄 Последний автопоиск: <b>{st.get('last_discovery_count',0)}</b> источников\n"
        f"⏸ Автопауза: <b>{st.get('auto_paused_count',0)}</b>\n\n"
        "Scanner сам обновляет каталог источников по расписанию. Подключённые группы слушаются в реальном времени, а сильные лиды приходят отдельным уведомлением."
        f"{setup}{err}",
        reply_markup=scanner_menu()
    )
    await c.answer()

@dp.callback_query(F.data=='scan:discover')
async def scan_discover(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    if not scanner or not scanner.enabled:
        return await c.answer('Сначала настрой TG_API_ID / TG_API_HASH / TG_SESSION',show_alert=True)
    await c.answer('Расширенный поиск крипто-групп…')
    try:
        rows=await scanner.discover()
    except Exception as e:
        return await c.message.answer(f'⚠️ Scanner: {html.escape(str(e))}')
    saved=await db.scanner_sources('DISCOVERED',20)
    await c.message.answer(
        f'🔭 <b>ПОИСК ЗАВЕРШЁН</b>\n\nНайдено в этом проходе: <b>{len(rows)}</b>\n'
        'Ниже лучшие публичные группы. Нажми на нужную — аккаунт подключится к ней и Scanner начнёт слушать новые сообщения.',
        reply_markup=source_rows(saved,'found')
    )

@dp.callback_query(F.data=='scan:activate3')
async def scan_activate_three(c):
    if not scanner or not scanner.enabled:
        return await c.answer('Scanner не настроен',show_alert=True)
    rows=await db.scanner_sources('DISCOVERED',3)
    if not rows:
        return await c.answer('Сначала найди источники',show_alert=True)
    await c.answer('Подключаю до 3 источников…')
    ok=[]; errors=[]
    for r in rows:
        try:
            src=await scanner.activate_source(r['id'])
            ok.append('@'+src['username'])
            await asyncio.sleep(2)
        except Exception as e:
            errors.append(f"@{r['username']}: {type(e).__name__}")
            if 'подождать' in str(e).lower() or 'flood' in str(e).lower():
                break
    text='✅ <b>ПОДКЛЮЧЕНИЕ ИСТОЧНИКОВ</b>\n\n'
    text+=('Подключены: '+', '.join(html.escape(x) for x in ok)) if ok else 'Ничего не подключено.'
    if errors:
        text+='\n⚠️ '+html.escape('; '.join(errors))
    await c.message.answer(text,reply_markup=scanner_menu())

@dp.callback_query(F.data=='scan:found')
async def scan_found(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    rows=await db.scanner_sources('DISCOVERED',20)
    await c.message.answer(
        '🗂 <b>НАЙДЕННЫЕ ИСТОЧНИКИ</b>\n\n'+('Выбери группы для подключения.' if rows else 'Пока пусто — нажми 🔭 «Найти крипто-чаты».'),
        reply_markup=source_rows(rows,'found')
    )
    await c.answer()

@dp.callback_query(F.data=='scan:active')
async def scan_active(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    rows=await db.scanner_sources('ACTIVE',20)
    text='\n'.join(
        f"• @{html.escape(r['username'])} · 👁 {r['messages_seen']} · 🔥 {r['leads_found']}"
        for r in rows
    ) or 'Активных источников пока нет.'
    await c.message.answer(
        f'📡 <b>ПОДКЛЮЧЁННЫЕ</b>\n\n{text}\n\n👁 — просмотрено сообщений · 🔥 — кандидатов добавлено',
        reply_markup=source_rows(rows,'active')
    )
    await c.answer()

@dp.callback_query(F.data=='scan:performance')
async def scan_performance(c):
    rows=await db.scanner_performance(15)
    if not rows:
        text='Пока недостаточно данных.'
    else:
        parts=[]
        for i,r in enumerate(rows,1):
            parts.append(
                f"{i}. <b>@{html.escape(r['username'])}</b> · {r['status']}\n"
                f"   👁 {r['messages_seen']} · 🔥 {r['attributed_leads']} · "
                f"↩️ {r['replied']} · 💵 {r['approved']} · {r['leads_per_1k']}/1k"
            )
        text='\n'.join(parts)
    await c.message.answer(
        '🏆 <b>ЭФФЕКТИВНОСТЬ ИСТОЧНИКОВ</b>\n\n'+text+
        '\n\n🔥 — найдено кандидатов · ↩️ — ответили · 💵 — засчитано · /1k — лидов на 1000 сообщений',
        reply_markup=scanner_menu()
    )
    await c.answer()

@dp.callback_query(F.data.startswith('src:on:'))
async def source_on(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    if not scanner or not scanner.enabled:
        return await c.answer('Scanner не настроен',show_alert=True)
    sid=int(c.data.split(':')[2])
    await c.answer('Подключаю…')
    try:
        src=await scanner.activate_source(sid)
        await c.message.answer(
            f"✅ <b>{html.escape(src['title'])}</b> подключён.\n"
            f"Scanner теперь следит за новыми сообщениями в @{html.escape(src['username'])}.",
            reply_markup=scanner_menu()
        )
    except Exception as e:
        await c.message.answer(f'⚠️ Не удалось подключить: {html.escape(str(e))}')

@dp.callback_query(F.data.startswith('src:pause:'))
async def source_pause(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    sid=int(c.data.split(':')[2])
    if scanner: await scanner.pause_source(sid)
    else: await db.set_scanner_source_status(sid,'PAUSED')
    await c.answer('Поставлен на паузу')
    await c.message.answer('⏸ Источник больше не добавляет новых кандидатов.',reply_markup=scanner_menu())

@dp.callback_query(F.data=='hook_help')
async def hook_help_cb(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    await c.message.answer(
        '🧲 <b>ЗАЦЕПИТЬ</b>\n\n'
        'Команда: <code>/hook LEAD_ID</code>\n'
        'Для обычных лидов Polza сделает 3 живых захода. Для лидов Scanner используются локальные контекстные шаблоны: вопрос, ценность и прямой вариант.'
    )
    await c.answer()

@dp.callback_query(F.data=='help_add')
async def help_cb(c):
    await c.message.answer('➕ /add @username | источник | контекст\n🔎 /find — отбор пачки кандидатов\n🧲 /hook LEAD_ID — 3 сильных захода\n📦 /import — массово\n🤖 /ai LEAD_ID | входящее сообщение\n💼 /offer Название | ставка | рефка\n🏷 /campaign Название | OFFER_ID\n📋 /report — отчёт за сутки'); await c.answer()

@dp.callback_query(F.data=='aihelp')
async def aih(c): await c.message.answer('🤖 <code>/ai LEAD_ID | его сообщение</code>\n\nAI даст 3 коротких варианта ответа.'); await c.answer()

@dp.callback_query(F.data=='next')
async def nxt(c): await c.answer(); await show_next(c.message)

@dp.callback_query(F.data.startswith('hook:'))
async def hook_button(c):
    if not allowed(c.from_user.id): return await c.answer('Нет доступа',show_alert=True)
    lid=int(c.data.split(':')[1]); l=await db.get(lid)
    if not l: return await c.answer('Лид не найден',show_alert=True)
    await c.answer('Генерирую…')
    if (l['source'] or '').startswith('scanner:'):
        hooks='\n'.join(f'{chr(65+i)}) {x}' for i,x in enumerate(contextual_hooks(l)))
    else:
        hooks=await outreach_hooks(l['context'],l['source'])
    await c.message.answer(
        f'🧲 <b>Заходы для @{html.escape(l["username"])}</b>\n\n{html.escape(hooks)}'
    )

@dp.callback_query(F.data.startswith('t:'))
async def txt(c):
    _,v,lid=c.data.split(':'); l=await db.get(int(lid)); await db.set_variant(int(lid),v)
    await c.message.answer(f'💬 <b>Вариант {v}</b>\n\n<code>{script(l,v)}</code>'); await c.answer()

@dp.callback_query(F.data.startswith('s:'))
async def status(c):
    _,s,lid=c.data.split(':'); await db.status(int(lid),s)
    if s in ('NOT_INTERESTED','SKIPPED','INVALID','PAID'): await db.clear_followup(int(lid))
    await c.answer('Сохранено'); await c.message.answer(f'✅ Lead #{lid}: <b>{s}</b>',reply_markup=menu())

@dp.callback_query(F.data.startswith('link:'))
async def link(c):
    lid=int(c.data.split(':')[1]); l=await db.get(lid); ref=l['referral_link'] or REF
    if not ref: return await c.message.answer('⚠️ Для оффера не задана реферальная ссылка.')
    await db.status(lid,'LINK_SENT'); await c.message.answer(f'🔗 <b>Реферальная ссылка</b>\n<code>{ref}</code>'); await c.answer('LINK_SENT')

@dp.callback_query(F.data.startswith('f:'))
async def fu(c):
    _,h,lid=c.data.split(':'); await db.schedule_followup(int(lid),int(h)); await c.answer('Поставлен'); await c.message.answer(f'⏰ Lead #{lid}: через {h}ч')

@dp.callback_query(F.data=='followups')
async def fus(c):
    rows=await db.due_followups(); await c.message.answer('⏰ <b>FOLLOW-UP</b>\n\n'+('\n'.join(f"@{r['username']} · {r['status']} · {r['source']}" for r in rows) if rows else 'Сейчас ничего нет.'),reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='stats')
async def stats(c): await c.message.answer(await report_text(),reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='report')
async def report_cb(c): await c.message.answer(await report_text(1),reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='sources')
async def sources(c):
    rows=await db.source_stats(); await c.message.answer('📍 <b>ИСТОЧНИКИ</b>\n\n'+('\n'.join(f"{r['source']}: {r['contacted']} contact · {r['replied']} reply · {r['approved']} approved" for r in rows) if rows else 'Нет данных'),reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='ab')
async def ab(c):
    rows=await db.variant_stats(); await c.message.answer('🧪 <b>A/B</b>\n\n'+('\n'.join(f"{r['variant']}: {r['contacted']} sent · {r['replied']} reply · {r['approved']} approved" for r in rows) if rows else 'Нет данных'),reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='offers')
async def offers(c):
    rows=await db.offers(); camps=await db.campaigns(); t='💼 <b>ОФФЕРЫ</b>\n'+''.join(f"\n#{r['id']} {r['name']} · ${float(r['rate']):.2f}" for r in rows); t+='\n\n🏷 <b>КАМПАНИИ</b>'+(''.join(f"\n#{x['id']} {x['name']} → {x['offer_name']}" for x in camps) or '\n—'); await c.message.answer(t); await c.answer()

@dp.callback_query(F.data=='money')
async def money(c):
    s=await db.stats(RATE); await c.message.answer(f"💰 <b>MONEY</b>\n\nЗасчитано: {s['approved']} (${float(s['revenue']):.2f})\nОплачено: {s['paid']} (${float(s['paid_value']):.2f})\nОжидается: ${float(s['revenue']-s['paid_value']):.2f}\n\nПосле выплаты: /paid",reply_markup=menu()); await c.answer()

@dp.callback_query(F.data=='export')
async def export(c):
    rows=await db.export_rows(); out=io.StringIO(); fields=list(rows[0].keys()) if rows else ['id','username']; w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
    for r in rows: w.writerow(dict(r))
    data=out.getvalue().encode('utf-8-sig'); await c.message.answer_document(BufferedInputFile(data,filename='traffic_os_leads.csv'),caption='📤 Экспорт Traffic OS'); await c.answer()

@dp.callback_query(F.data=='dashboard')
async def dashboard(c):
    if PUBLIC_URL:
        url=f'{PUBLIC_URL}/?token={DASH_TOKEN}' if DASH_TOKEN else PUBLIC_URL
        await c.message.answer(f'🌐 <b>Dashboard</b>\n{url}')
    else:
        await c.message.answer('🌐 Добавь PUBLIC_URL после выдачи домена Railway. Dashboard уже слушает PORT.')
    await c.answer()

@dp.message(Command('paid'))
async def paid(m:Message):
    if allowed(m.from_user.id): await db.mark_paid_all(); await m.answer('✅ Все неоплаченные APPROVED отмечены как оплаченные.',reply_markup=menu())

async def daily_report_loop(bot):
    tz=ZoneInfo(TZ_NAME)
    while True:
        try:
            now=datetime.now(tz); key=f'daily_report:{now.date().isoformat()}'; sent=await db.get_state(key)
            if now.hour==REPORT_HOUR and not sent:
                text=await report_text(1)
                for uid in ADMINS:
                    try: await bot.send_message(uid,text)
                    except Exception: pass
                await db.set_state(key,'1')
        except Exception: pass
        await asyncio.sleep(60)

async def run_web():
    app=create_app(db,RATE)
    server=uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=PORT,log_level='info',access_log=False))
    await server.serve()

async def main():
    global DEFAULT_OFFER_ID, scanner
    if not TOKEN or not DBURL or not ADMINS: raise RuntimeError('Set BOT_TOKEN, DATABASE_URL and ADMIN_IDS')
    await db.connect(); o=await db.ensure_default_offer(OFFER,RATE,REF); DEFAULT_OFFER_ID=o['id']
    bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    async def strong_lead_alert(lead, src, context, score):
        preview=html.escape((context or '')[:500])
        markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🧲 Заходы',callback_data=f"hook:{lead['id']}"),
             InlineKeyboardButton(text='🎯 Открыть очередь',callback_data='next')],
            [InlineKeyboardButton(text='🚫 Пропустить',callback_data=f"s:SKIPPED:{lead['id']}")]
        ])
        text=(
            f"🔥 <b>СИЛЬНЫЙ ЛИД · {score}/100</b>\n\n"
            f"👤 @{html.escape(lead['username'])}\n"
            f"📍 @{html.escape(src['username'])}\n\n"
            f"💬 {preview}"
        )
        for uid in ADMINS:
            try:
                await bot.send_message(uid,text,reply_markup=markup)
            except Exception:
                pass

    scanner=TelegramScanner(db,score_ctx,DEFAULT_OFFER_ID,strong_lead_alert)
    scanner_started=await scanner.start()
    tasks=[asyncio.create_task(run_web()),asyncio.create_task(daily_report_loop(bot))]
    if scanner_started:
        tasks.append(asyncio.create_task(scanner.maintenance_loop()))
    try: await dp.start_polling(bot)
    finally:
        for t in tasks: t.cancel()
        if scanner: await scanner.stop()
        await db.close()

if __name__=='__main__': asyncio.run(main())
