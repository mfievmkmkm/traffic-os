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
- AI reply assistant using OpenAI Responses API with `store=False`
- Follow-up queue
- Payment accounting
- CSV export in Telegram and on web

## Railway deploy
1. Create a Railway project and PostgreSQL service.
2. Deploy this folder/repository as the app service.
3. Add variables from `.env.example`.
4. Set start command to `python -m app.main` (the included Procfile already does this).
5. Generate a public Railway domain and put it into `PUBLIC_URL`, e.g. `https://your-app.up.railway.app`.
6. Set Railway healthcheck path to `/health`.
7. Open the bot and press **🌐 Dashboard**.

The dashboard is protected by `DASHBOARD_TOKEN`. Use a long random value and do not publish a URL containing the token.

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

The dashboard is now mobile-first and includes:
- compact sidebar / bottom mobile navigation;
- KPI cards and 14-day activity chart;
- conversion funnel;
- quick lead creation from the web panel;
- inline lead status updates;
- source and A/B performance tables;
- CSV export and responsive layout.

Open `PUBLIC_URL/?token=YOUR_DASHBOARD_TOKEN`.
