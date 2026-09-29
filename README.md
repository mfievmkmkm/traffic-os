# Traffic OS V6

Private Telegram CRM for consent-respecting traffic operations. First-contact sending remains manual; the system automates organization, prioritization, follow-up reminders, analytics and reply assistance.

## V5 additions
- Built-in mobile-friendly web dashboard on the same Railway service
- `/health` endpoint for Railway health checks
- Token-protected dashboard and CSV web export
- Automatic daily Telegram report to admins
- 14-day activity chart, source analytics, A/B analytics, recent-leads table
- Safer status transitions and follow-up cleanup
- Campaign / offer analytics groundwork
- PostgreSQL indexes and persistent app state

## Existing features
- PostgreSQL lead CRM + username deduplication
- Multiple offers/campaigns, per-offer rate and referral link
- Lead score from supplied context
- A/B first-message drafts
- AI reply assistant via Polza.ai using an OpenAI-compatible API
- Follow-up queue
- Payment accounting
- CSV export in Telegram and on web

## V6 Telegram Scanner
- Telethon user-client scanner for public crypto discussion groups
- Source discovery by configurable crypto/trading search queries
- One-click source approval from the bot; no blind auto-joining
- Watches only approved sources and only new group messages
- Keyword/topic relevance scoring; no protected-trait targeting
- Stores source/message evidence for each scanner lead
- Deduplicates by Telegram username and prioritizes by score
- Scanner-sourced opening messages are generated locally from broad topical signals; raw scanner content is not sent to the LLM
- Manual first contact only; no bulk unsolicited DM sender

### Scanner setup
1. Create your Telegram API application at my.telegram.org → API development tools.
2. Keep `TG_API_ID` and `TG_API_HASH` private.
3. Generate a StringSession once on a trusted computer:
   `python -m app.session_setup`
4. Put the resulting value in Railway as `TG_SESSION`. Treat it like a password.
5. Redeploy and open **🔎 Lead Finder** → **🔭 Найти крипто-чаты**.
6. Review discovered public groups and press **➕** only on sources you want to monitor.

Required scanner variables:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION`

Optional:
- `SCANNER_QUERIES`
- `SCANNER_MIN_SCORE=55`
- `SCANNER_CONTEXT_CHARS=1200`

Telegram API usage is subject to Telegram's API Terms. Do not use the scanner for flooding, spam, participant scraping, automated unsolicited DMs, or evading platform restrictions.

## Railway deploy
1. Create a Railway project and PostgreSQL service.
2. Deploy this repository as the app service.
3. Add variables from `.env.example`.
4. Start command: `python -m app.main`.
5. Generate a public Railway domain and put it into `PUBLIC_URL`.
6. Set Railway healthcheck path to `/health`.
7. Open the bot and press **🖥 Панель**.

The dashboard is protected by `DASHBOARD_TOKEN`. Use a long random value and do not publish a URL containing the token.

## AI / Polza.ai
Set these Railway variables:
- `LLM_API_KEY` — your Polza API key
- `LLM_BASE_URL=https://polza.ai/api/v1`
- `LLM_MODEL=deepseek/deepseek-v4-flash`

The API key must only be stored in Railway variables / local `.env`, never committed to GitHub.

## Commands
- `/add @username | source | context`
- `/import` then one `@username | source | context` per line
- `/ai LEAD_ID | inbound message`
- `/offer Name | 0.70 | referral_link`
- `/campaign Name | OFFER_ID`
- `/report`
- `/paid`

## Environment
See `.env.example`.

## Operating model
Use topical relevance, language, activity and campaign/source performance for prioritization. Do not use protected traits for targeting. Respect opt-outs and platform anti-spam rules.

## V5 interface
The dashboard is mobile-first and includes KPI cards, a 14-day activity chart, conversion funnel, quick lead creation, inline status updates, source/A-B analytics and CSV export.

Open `PUBLIC_URL/?token=YOUR_DASHBOARD_TOKEN`.
