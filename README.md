# Traffic OS V5

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
