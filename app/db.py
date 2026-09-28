import asyncpg

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS offers(
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  rate NUMERIC(12,4) NOT NULL DEFAULT .70,
  referral_link TEXT DEFAULT '',
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS campaigns(
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  offer_id BIGINT REFERENCES offers(id),
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads(
  id BIGSERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  source TEXT DEFAULT 'manual',
  context TEXT DEFAULT '',
  score INTEGER DEFAULT 0 CHECK(score BETWEEN 0 AND 100),
  status TEXT DEFAULT 'NEW',
  script_variant TEXT,
  offer_id BIGINT REFERENCES offers(id),
  campaign_id BIGINT REFERENCES campaigns(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  contacted_at TIMESTAMPTZ,
  replied_at TIMESTAMPTZ,
  interested_at TIMESTAMPTZ,
  link_sent_at TIMESTAMPTZ,
  joined_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  followup_at TIMESTAMPTZ,
  notes TEXT DEFAULT ''
);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS offer_id BIGINT REFERENCES offers(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_id BIGINT REFERENCES campaigns(id);
CREATE TABLE IF NOT EXISTS dialogue_notes(
  id BIGSERIAL PRIMARY KEY,
  lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
  inbound TEXT NOT NULL,
  suggestion TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_state(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_followup ON leads(followup_at);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);
CREATE INDEX IF NOT EXISTS idx_leads_offer ON leads(offer_id);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
'''

class DB:
    def __init__(self, url):
        self.url = url
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=8, command_timeout=30)
        async with self.pool.acquire() as c:
            await c.execute(SCHEMA)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def ping(self):
        return await self.pool.fetchval('SELECT 1') == 1

    async def ensure_default_offer(self, name, rate, ref):
        return await self.pool.fetchrow(
            """INSERT INTO offers(name,rate,referral_link) VALUES($1,$2,$3)
               ON CONFLICT(name) DO UPDATE SET rate=EXCLUDED.rate,
               referral_link=CASE WHEN EXCLUDED.referral_link<>'' THEN EXCLUDED.referral_link ELSE offers.referral_link END
               RETURNING *""", name, rate, ref)

    async def add_offer(self, name, rate, ref=''):
        return await self.pool.fetchrow(
            """INSERT INTO offers(name,rate,referral_link) VALUES($1,$2,$3)
               ON CONFLICT(name) DO UPDATE SET rate=EXCLUDED.rate,referral_link=EXCLUDED.referral_link RETURNING *""",
            name, rate, ref)

    async def offers(self):
        return await self.pool.fetch('SELECT * FROM offers WHERE active ORDER BY id')

    async def add_campaign(self, name, offer_id):
        return await self.pool.fetchrow(
            """INSERT INTO campaigns(name,offer_id) VALUES($1,$2)
               ON CONFLICT(name) DO UPDATE SET offer_id=EXCLUDED.offer_id RETURNING *""", name, offer_id)

    async def campaigns(self):
        return await self.pool.fetch(
            """SELECT c.*,o.name offer_name FROM campaigns c LEFT JOIN offers o ON o.id=c.offer_id
               WHERE c.active ORDER BY c.id""")

    async def add_lead(self, username, source='manual', context='', score=0, offer_id=None, campaign_id=None):
        username = username.strip().lstrip('@').lower()
        if not username:
            raise ValueError('empty username')
        return await self.pool.fetchrow(
            """INSERT INTO leads(username,source,context,score,offer_id,campaign_id)
               VALUES($1,$2,$3,$4,$5,$6)
               ON CONFLICT(username) DO UPDATE SET
                 context=CASE WHEN EXCLUDED.context<>'' THEN EXCLUDED.context ELSE leads.context END,
                 source=CASE WHEN EXCLUDED.source<>'' THEN EXCLUDED.source ELSE leads.source END,
                 score=GREATEST(leads.score,EXCLUDED.score),
                 offer_id=COALESCE(EXCLUDED.offer_id,leads.offer_id),
                 campaign_id=COALESCE(EXCLUDED.campaign_id,leads.campaign_id)
               RETURNING *""", username, source, context, score, offer_id, campaign_id)

    async def next_lead(self):
        return await self.pool.fetchrow(
            """SELECT l.*,o.name offer_name,o.rate,o.referral_link,c.name campaign_name
               FROM leads l LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN campaigns c ON c.id=l.campaign_id
               WHERE l.status='NEW' ORDER BY l.score DESC,l.created_at LIMIT 1""")

    async def get(self, lid):
        return await self.pool.fetchrow(
            """SELECT l.*,o.name offer_name,o.rate,o.referral_link,c.name campaign_name
               FROM leads l LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN campaigns c ON c.id=l.campaign_id
               WHERE l.id=$1""", lid)

    async def status(self, lid, status):
        allowed = {'NEW','CONTACTED','REPLIED','INTERESTED','LINK_SENT','JOINED','APPROVED','PAID','NOT_INTERESTED','SKIPPED','INVALID'}
        if status not in allowed:
            raise ValueError('invalid status')
        col = {'CONTACTED':'contacted_at','REPLIED':'replied_at','INTERESTED':'interested_at','LINK_SENT':'link_sent_at','JOINED':'joined_at','APPROVED':'approved_at','PAID':'paid_at'}.get(status)
        if col:
            await self.pool.execute(f'UPDATE leads SET status=$1,{col}=COALESCE({col},now()) WHERE id=$2', status, lid)
        else:
            await self.pool.execute('UPDATE leads SET status=$1 WHERE id=$2', status, lid)

    async def set_variant(self, lid, variant):
        await self.pool.execute('UPDATE leads SET script_variant=$1 WHERE id=$2', variant, lid)

    async def schedule_followup(self, lid, hours=24):
        await self.pool.execute("UPDATE leads SET followup_at=now()+make_interval(hours=>$1) WHERE id=$2", int(hours), lid)

    async def clear_followup(self, lid):
        await self.pool.execute('UPDATE leads SET followup_at=NULL WHERE id=$1', lid)

    async def due_followups(self, limit=30):
        return await self.pool.fetch(
            """SELECT l.*,o.name offer_name FROM leads l LEFT JOIN offers o ON o.id=l.offer_id
               WHERE l.followup_at<=now() AND l.status IN ('REPLIED','INTERESTED','LINK_SENT')
               ORDER BY l.followup_at LIMIT $1""", limit)

    async def mark_paid_all(self):
        return await self.pool.execute("UPDATE leads SET status='PAID',paid_at=COALESCE(paid_at,now()) WHERE approved_at IS NOT NULL AND paid_at IS NULL")

    async def save_dialogue(self, lid, inbound, suggestion):
        await self.pool.execute('INSERT INTO dialogue_notes(lead_id,inbound,suggestion) VALUES($1,$2,$3)', lid, inbound, suggestion)

    async def stats(self, default_rate, days=None):
        where = ''
        args = [default_rate]
        if days:
            where = 'WHERE l.created_at >= now()-make_interval(days=>$2)'
            args.append(int(days))
        r = await self.pool.fetchrow(f"""
            SELECT count(*) total,
              count(*) FILTER(WHERE contacted_at IS NOT NULL) contacted,
              count(*) FILTER(WHERE replied_at IS NOT NULL) replied,
              count(*) FILTER(WHERE interested_at IS NOT NULL) interested,
              count(*) FILTER(WHERE link_sent_at IS NOT NULL) link_sent,
              count(*) FILTER(WHERE joined_at IS NOT NULL) joined,
              count(*) FILTER(WHERE approved_at IS NOT NULL) approved,
              count(*) FILTER(WHERE paid_at IS NOT NULL) paid,
              count(*) FILTER(WHERE status='NEW') new,
              COALESCE(sum(COALESCE(o.rate,$1)) FILTER(WHERE l.approved_at IS NOT NULL),0) revenue,
              COALESCE(sum(COALESCE(o.rate,$1)) FILTER(WHERE l.paid_at IS NOT NULL),0) paid_value
            FROM leads l LEFT JOIN offers o ON o.id=l.offer_id {where}""", *args)
        return dict(r)

    async def source_stats(self, limit=20):
        return await self.pool.fetch("""
            SELECT source,count(*) total,
              count(*) FILTER(WHERE contacted_at IS NOT NULL) contacted,
              count(*) FILTER(WHERE replied_at IS NOT NULL) replied,
              count(*) FILTER(WHERE approved_at IS NOT NULL) approved
            FROM leads GROUP BY source ORDER BY approved DESC,total DESC LIMIT $1""", limit)

    async def variant_stats(self):
        return await self.pool.fetch("""
            SELECT COALESCE(script_variant,'—') variant,
              count(*) FILTER(WHERE contacted_at IS NOT NULL) contacted,
              count(*) FILTER(WHERE replied_at IS NOT NULL) replied,
              count(*) FILTER(WHERE approved_at IS NOT NULL) approved
            FROM leads GROUP BY script_variant ORDER BY contacted DESC""")

    async def campaign_stats(self):
        return await self.pool.fetch("""
            SELECT COALESCE(c.name,'Без кампании') campaign,COALESCE(o.name,'Default') offer,
              count(*) total,count(*) FILTER(WHERE l.contacted_at IS NOT NULL) contacted,
              count(*) FILTER(WHERE l.approved_at IS NOT NULL) approved,
              COALESCE(sum(o.rate) FILTER(WHERE l.approved_at IS NOT NULL),0) revenue
            FROM leads l LEFT JOIN campaigns c ON c.id=l.campaign_id LEFT JOIN offers o ON o.id=l.offer_id
            GROUP BY c.name,o.name ORDER BY approved DESC,total DESC""")

    async def daily_series(self, days=14, default_rate=.70):
        return await self.pool.fetch("""
            WITH d AS (SELECT generate_series(current_date-$1::int+1,current_date,'1 day'::interval)::date day)
            SELECT d.day,
              count(l.id) FILTER(WHERE l.contacted_at::date=d.day) contacted,
              count(l.id) FILTER(WHERE l.replied_at::date=d.day) replied,
              count(l.id) FILTER(WHERE l.approved_at::date=d.day) approved,
              COALESCE(sum(COALESCE(o.rate,$2)) FILTER(WHERE l.approved_at::date=d.day),0) revenue
            FROM d LEFT JOIN leads l ON l.created_at::date<=d.day LEFT JOIN offers o ON o.id=l.offer_id
            GROUP BY d.day ORDER BY d.day""", int(days), default_rate)

    async def recent_leads(self, limit=50):
        return await self.pool.fetch("""
            SELECT l.id,l.username,l.source,l.score,l.status,l.script_variant,l.created_at,
                   o.name offer,c.name campaign
            FROM leads l LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN campaigns c ON c.id=l.campaign_id
            ORDER BY l.id DESC LIMIT $1""", limit)

    async def export_rows(self):
        return await self.pool.fetch("""
            SELECT l.id,l.username,l.source,l.context,l.score,l.status,l.script_variant,
                   o.name offer,c.name campaign,l.created_at,l.contacted_at,l.replied_at,l.interested_at,
                   l.link_sent_at,l.joined_at,l.approved_at,l.paid_at,l.followup_at,l.notes
            FROM leads l LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN campaigns c ON c.id=l.campaign_id
            ORDER BY l.id""")

    async def set_state(self, key, value):
        await self.pool.execute("""INSERT INTO app_state(key,value) VALUES($1,$2)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()""", key, str(value))

    async def get_state(self, key):
        return await self.pool.fetchval('SELECT value FROM app_state WHERE key=$1', key)
