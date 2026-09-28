import os, csv, io, html
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

DASH_TOKEN = os.getenv('DASHBOARD_TOKEN','')

STATUS_LABELS = {
    'NEW':'Новый','CONTACTED':'Написал','REPLIED':'Ответил','INTERESTED':'Интерес',
    'LINK_SENT':'Ссылка','JOINED':'Подписался','APPROVED':'Засчитан','PAID':'Оплачен',
    'NOT_INTERESTED':'Не интересно','SKIPPED':'Пропущен','INVALID':'Невалид'
}

CSS = r'''
:root{color-scheme:dark;--bg:#070910;--panel:#0d111b;--panel2:#111827;--soft:#171e2d;--line:#202a3c;--text:#f7f9fc;--muted:#8f9bb3;--accent:#7c6cff;--accent2:#55b8ff;--green:#5ee0a0;--amber:#ffc766;--red:#ff7185;--shadow:0 24px 70px rgba(0,0,0,.28)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(900px 600px at 10% -10%,rgba(124,108,255,.18),transparent 60%),radial-gradient(700px 500px at 100% 10%,rgba(85,184,255,.10),transparent 55%),var(--bg);font:14px Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--text)}
button,input,select{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:240px minmax(0,1fr)}.side{position:sticky;top:0;height:100vh;padding:22px 16px;border-right:1px solid var(--line);background:rgba(7,9,16,.72);backdrop-filter:blur(18px)}.logo{display:flex;align-items:center;gap:11px;padding:8px 10px 24px;font-weight:900;font-size:18px}.logoMark{width:36px;height:36px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(135deg,var(--accent),var(--accent2));box-shadow:0 10px 30px rgba(124,108,255,.3)}.nav{display:grid;gap:5px}.nav a{color:var(--muted);text-decoration:none;padding:11px 12px;border-radius:11px;font-weight:650}.nav a:hover,.nav a.active{background:var(--soft);color:var(--text)}.sideFoot{position:absolute;left:16px;right:16px;bottom:20px;color:var(--muted);font-size:12px;line-height:1.5}.main{min-width:0;padding:28px 30px 60px;max-width:1500px;width:100%;margin:auto}.top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:22px}.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:800}.title{font-size:30px;line-height:1.15;font-weight:900;letter-spacing:-.03em;margin-top:5px}.subtitle{color:var(--muted);margin-top:7px}.topActions{display:flex;gap:8px;flex-wrap:wrap}.btn{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--text);padding:10px 13px;border-radius:11px;text-decoration:none;font-weight:750;cursor:pointer;transition:.18s}.btn:hover{transform:translateY(-1px);border-color:#39465f}.btn.primary{border:0;background:linear-gradient(135deg,var(--accent),#5f8dff);box-shadow:0 10px 28px rgba(124,108,255,.25)}.btn.ghost{background:transparent}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:linear-gradient(180deg,rgba(17,24,39,.86),rgba(13,17,27,.9));border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}.kpi{padding:18px}.kpiTop{display:flex;justify-content:space-between;gap:8px;color:var(--muted);font-size:12px;font-weight:750}.ico{width:30px;height:30px;display:grid;place-items:center;background:var(--soft);border-radius:9px}.num{font-size:30px;font-weight:900;letter-spacing:-.04em;margin:7px 0 4px}.delta{font-size:12px;color:var(--muted)}.green{color:var(--green)}.amber{color:var(--amber)}.section{margin-top:14px}.two{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(320px,.75fr);gap:14px}.cardHead{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:17px 18px 0}.cardTitle{font-weight:850;font-size:15px}.cardSub{font-size:12px;color:var(--muted);margin-top:3px}.chart{height:230px;padding:22px 18px 15px;display:flex;align-items:flex-end;gap:7px}.barWrap{height:100%;flex:1;min-width:0;display:flex;flex-direction:column;justify-content:flex-end}.barTrack{height:180px;display:flex;align-items:flex-end}.bar{width:100%;min-height:3px;border-radius:7px 7px 3px 3px;background:linear-gradient(180deg,var(--accent2),var(--accent));box-shadow:0 8px 20px rgba(124,108,255,.16)}.lab{text-align:center;color:var(--muted);font-size:9px;margin-top:7px;white-space:nowrap}.funnel{padding:18px;display:grid;gap:12px}.frow{display:grid;grid-template-columns:100px 1fr 42px;align-items:center;gap:10px}.fname{color:var(--muted);font-size:12px}.track{height:9px;background:#0a0e16;border-radius:99px;overflow:hidden}.fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--accent),var(--accent2))}.fval{text-align:right;font-weight:800}.quick{padding:18px}.formGrid{display:grid;grid-template-columns:1.05fr .9fr 1.8fr auto;gap:8px;margin-top:12px}.field{width:100%;min-width:0;background:#090d15;color:var(--text);border:1px solid var(--line);border-radius:11px;padding:11px 12px;outline:none}.field:focus{border-color:#56648a;box-shadow:0 0 0 3px rgba(124,108,255,.09)}.msg{min-height:18px;margin-top:9px;font-size:12px;color:var(--muted)}.tableWrap{overflow:auto;padding:8px 12px 14px}.tbl{width:100%;border-collapse:collapse;min-width:720px}.tbl th,.tbl td{padding:11px 9px;border-bottom:1px solid rgba(32,42,60,.75);text-align:left;white-space:nowrap}.tbl th{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.user{font-weight:800}.source{color:var(--muted)}.score{font-weight:850}.pill{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--line);border-radius:999px;background:#0a0e16;font-size:11px}.dot{width:6px;height:6px;border-radius:50%;background:var(--accent2)}.miniSelect{background:#090d15;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:11px}.smallGrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.empty{color:var(--muted);padding:18px}.toast{position:fixed;right:20px;bottom:20px;padding:12px 14px;background:#151d2b;border:1px solid #31405a;border-radius:12px;box-shadow:var(--shadow);opacity:0;transform:translateY(10px);pointer-events:none;transition:.2s;z-index:50}.toast.show{opacity:1;transform:none}.mobileNav{display:none}
@media(max-width:1050px){.shell{grid-template-columns:1fr}.side{display:none}.main{padding:20px 18px 90px}.mobileNav{position:fixed;display:flex;z-index:40;bottom:12px;left:12px;right:12px;background:rgba(13,17,27,.92);border:1px solid var(--line);border-radius:16px;padding:7px;backdrop-filter:blur(16px);box-shadow:var(--shadow);justify-content:space-around}.mobileNav a{color:var(--muted);text-decoration:none;padding:8px 10px;font-size:11px;text-align:center}.mobileNav b{display:block;color:var(--text);font-size:16px;margin-bottom:2px}}
@media(max-width:760px){.top{flex-direction:column}.title{font-size:26px}.kpis{grid-template-columns:repeat(2,1fr)}.two,.smallGrid{grid-template-columns:1fr}.formGrid{grid-template-columns:1fr}.chart{height:205px;padding-left:10px;padding-right:10px}.barTrack{height:155px}.topActions{width:100%}.topActions .btn{flex:1;text-align:center}.num{font-size:26px}.frow{grid-template-columns:86px 1fr 36px}}
'''

JS = r'''
const token = new URLSearchParams(location.search).get('token') || '';
const toast = (m, bad=false) => { const t=document.getElementById('toast'); t.textContent=m; t.style.borderColor=bad?'#713747':'#31405a'; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2200); };
async function addLead(){
  const username=document.getElementById('username').value.trim(), source=document.getElementById('source').value.trim(), context=document.getElementById('context').value.trim();
  if(!username){toast('Укажи @username',true);return}
  const r=await fetch('/api/leads?token='+encodeURIComponent(token),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,source,context})});
  const j=await r.json(); if(!r.ok){toast(j.detail||'Ошибка',htrue);return} toast('Лид добавлен'); setTimeout(()=>location.reload(),450);
}
async function setStatus(id, el){
  const status=el.value; const r=await fetch(`/api/leads/${id}/status?token=${encodeURIComponent(token)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});
  if(r.ok){toast('Статус сохранён'); el.closest('tr').querySelector('.statusText').textContent=el.options[el.selectedIndex].text} else toast('Не удалось сохранить',true);
}
'''

def _auth(token):
    if DASH_TOKEN and toke != DASH_TOKEN:
        raise HTTPException(401, 'Неверный токен панеи')

def _esc(v):
    return html.escape(str(v or ''))

def create_app(db, rate):
    app = FastAPI(title='Traffic OS Dashboard', docs_url=None, redoc_url=None)

    @app.get('/health')
    async def health():
        return {'ok': await db.ping(), 'service':'traffic-os'}

    @app.get('/api/stats')
    async def api_stats(token: str = Query(default='')):
        _auth(token); return await db.stats(rate)

    @app.post('/api/leads')
    async def api_add_lead(request: Request, token: str = Query(default='')):
        _auth(token); data = await request.json()
        username=(data.get('username') or '').strip(); source=(data.get('source') or 'dashboard').strip(); context=(data.get('context') or '').strip()
        if not username: raise HTTPException(400,'Нужен username')
        score=20
        x=context.lower()
        for k,n in [('btc',15),('битко',15),('фьюч',20),('трейд',20),('крипт',15),('рынок',10)]:
            if k in x: score += n
        row=await db.add_lead(username,source,context,min(score,100))
        return {'ok':True,'id':row['id'],'username':row['username']}

    @app.post('/api/leads/{lead_id}/status')
    async def api_status(lead_id: int, request: Request, token: str = Query(default='')):
        _auth(token); data=await request.json(); status=(data.get('status') or '').strip().upper()
        try: await db.status(lead_id,status)
        except ValueError: raise HTTPException(400,'Некорректный статус')
        return {'ok':True}

    @app.get('/export.csv')
    async def export_csv(token: str = Query(default='')):
        _auth(token); rows = await db.export_rows(); out = io.StringIO()
        fields = list(rows[0].keys())  if rows else ['id','username']; w = csv.DictWriter(out, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow(dict(r))
        data = io.BytesIO(out.getvalue().encode('utf-8-sig'))
        return StreamingResponse(data, media_type='text/csv', headers={'Content-Disposition':'attachment; filename=traffic_os_leads.csv'})

    @app.get('/', response_class=HTMLResponse)
    async def dashboard(token: str = Query(default='')):
        _auth(token)
        s=await db.stats(rate); src=await db.source_stats(8); ab=await db.variant_stats(); series=await db.daily_series(14,rate); recent=await db.recent_leads(30)
        contacted=int(s['contacted'] or 0); replied=int(s['replied'] or 0); interested=int(s['interested'] or 0); joined=int(s['joined'] or 0); approved=int(s['approved'] or 0); total=int(s['total'] or 0)
        maxv=max([int(x['contacted'] or 0) for x in series]+[1])
        bars=''.join(f'''<div class="barWrap" title="{x['day']}: {x['contacted']} контактов · {x['approved']} approved"><div class="barTrack"><div class="bar" style="height:{max(3,int((x['contacted'] or 0)/maxv*100))}%"></div></div><div class="lab">{str(x['day'])[5:]}</div></div>''' for x in series)
        funnel=[('Контакты',contacted),('Ответы',replied),('Интерес'interested),('Подписки',joined),('Approved',approved)]
        fmax=max(contacted,1)
        funnel_html=''.join(f'''<div class="frow"><div class="fname">{name}</div><div class="track"><div class="fill" style="width:{max(2,val/fmax*100):.1f}%"></div></div><div class="fval">{val}</div></div>''' for name,val in funnel)
        src_rows=''.join(f"<tr><td class='user'>{_esc(x['source'])}</td><td>{x['contacted']}</td><td>{x['replied']}</td><td class='green'>{x['approved']}</td></tr>" for x in src) or '<tr><td colspan="4" class="empty">Пока нет данных</td></tr>'
        ab_rows=''.join(f"<tr><td class='user'>{_esc(x['variant'])}</td><td>{x['contacted']}</td><td>{x['replied']}</td><td class='green'>{x['approved']}</td></tr>" for x in ab) or '<tr><td colspan="4" class="empty">Пока нет A/B данных</td></tr>'
        options=''.join(f'<option value="{k}">{v}</option>' for k,v in STATUS_LABELS.items())
        recent_rows=''
        for x in recent:
            current=STATUS_LABELS.get(x['status'],x['status'])
            lead_options=options.replace(f'value="{x["status"]}"',f'value="{x["status"]}" selected')
            recent_rows += f'''<tr><td>#{x['id']}</td><td class="user">@{_esc(x['username'])}</td><td class="source">{_esc(x['source'] or '—')}</td><td class="score">{x['score']}</td><td><span class="pill"><span class="dot"></span><span class="statusText">{_esc(current)}</span></span></td><td><select class="miniSelect" onchange="setStatus({x['id']},this)">{lead_options}</select></td></tr>'''
        if not recent_rows: recent_rows='<tr><td colspan="6" class="empty">Добавь первого лида выше 👆</td></tr>'
        t=_esc(token); conv=(approved/contacted*100 if contacted else 0); reply_rate=(replied/contacted*100 if contacted else 0); wait=float(s['revenue']-s['paid_value'])
        page=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#070910"><title>Traffic OS</title><style>{CSS}</style></head><body>
        <div class="shell"><aside class="side"><div class="logo"><div class="logoMark">⚡</div><span>Traffic OS</span></div><nav class="nav"><a class="active" href="#overview">◈ Обзор</a><a href="#work">◎ Быстрый старт</a><a href="#leads">◉ Лиды</a><a href="#sources">⌁ Источники</a><a href="#tests">A/B Тесты</a></nav><div class="sideFoot">CRM для ручной работы с релевантными лидами.<br>V5 · mobile-first</div></aside>
        <main class="main" id="overview"><div class="top"><div><div class="eyebrow">Рабочая панель</div><div class="title">Добрый вечер 👋</div><div class="subtitle">Вся воронка, деньги и очередь лидов — на одном экране.</div></div><div class="topActions"><a class="btn" href="/export.csv?token={t}">↗ CSV</a><a class="btn primary" href="/?token={t}">↻ Обновить</a></div></div>
        <section class="kpis"><div class="card kpi"><div class="kpiTop"><span>Всего лидов</span><span class="ico">👥</span></div><div class="num">{total}</div><div class="delta">В очереди <b>{s['new']}</b></div></div><div class="card kpi"><div class="kpiTop"><span>Контакты</span><span class="ico">💬</span></div><div class="num">{contacted}</div><div class="delta">Ответили <b>{replied}</b> · {reply_rate:.1f}%</div></div><div class="card kpi"><div class="kpiTop"><span>Approved</span><span class="ico">✓</span></div><div class="num green">{approved}</div><div class="delta">Конверсия <b>{conv:.1f}%</b></div></div><div class="card kpi"><div class="kpiTop"><span>Начислено</span><span class="ico">$</span></div><div class="num green">${float(s['revenue']):.2f}</div><div class="delta">Ждём <b class="amber">${wait:.2f}</b></div></div></section>
        <section class="section two"><div class="card"><div class="cardHead"><div><div class="cardTitle">Активность за 14 дней</div><div class="cardSub">Количество начатых контактов по дням</div></div></div><div class="chart">{bars}</div></div><div class="card"><div class="cardHead"><div><div class="cardTitle">Воронка</div><div class="cardSub">Где теряется конверсия</div></div></div><div class="funnel">{funnel_html}</div></div></section>
        <section class="section card quick" id="work"><div class="cardTitle">＋ Быстро добавить лида</div><div class="cardSub">Антидубли работают автоматически. Контекст нужен только для релевантности и подготовки сообщения.</div><div class="formGrid"><input class="field" id="username" placeholder="@username"><input class="field" id="source" placeholder="Источник"><input class="field" id="context" placeholder="Контекст: обсуждает BTC / фьючерсы…"><button class="btn primary" onclick="addLead()">Добавить</button></div><div class="msg">Совет: сначала добавляй только людей, у которых есть явный тематический контекст.</div></section>
        <section class="section card" id="leads"><div class="cardHead"><div><div class="cardTitle">Последние лиды</div><div class="cardSub">Статус можно менять прямо здесь — без команд в боте</div></div></div><div class="tableWrap"><table class="tbl"><tr><th>ID</th><th>Username</th><th>Источник</th><th>Score</th><th>Статус</th><th>Изменить</th></tr>{recent_rows}</table></div></section>
        <section class="section smallGrid"><div class="card" id="sources"><div class="cardHead"><div><div class="cardTitle">Лучшие источники</div><div class="cardSub">Смотри на approved, а не только на ответы</div></div></div><div class="tableWrap"><table class="tbl" style="min-width:0"><tr><th>Источник</th><th>Contact</th><th>Reply</th><th>Approved</th></tr>{src_rows}</table></div></div><div class="card" id="tests"><div class="cardHead"><div><div class="cardTitle">A/B сообщения</div><div class="cardSub">Сравнение вариантов по конечной конверсии</div></div></div><div class="tableWrap"><table class="tbl" style="min-width:0"><tr><th>Вариант</th><th>Contact</th><th>Reply</th><th>Approved</th></tr>{ab_rows}</table></div></div></section>
        </main></div><nav class="mobileNav"><a href="#overview"><b>◈</b>Обзор</a><a href="#work"><b>＋</b>Добавить</a><a href="#leads"><b>◉</b>Лиды</a><a href="#sources"><b>⌁</b>Источники</a></nav><div class="toast" id="toast"></div><script>{JS}</script></body></html>'''
        return HTMLResponse(page)
    return app
