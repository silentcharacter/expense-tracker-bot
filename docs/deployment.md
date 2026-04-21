# Deployment

Guide for deploying the bot (Cloud Function) and Mini App (GCS static hosting).

---

## Architecture

```
Telegram ──webhook──► Cloud Function (bot + /api/*)
                              ▲
Mini App (GCS) ──REST──────────┘
```

- **Cloud Function** — handles Telegram webhooks and serves the `/api/*` REST API.
- **GCS bucket** — hosts the Mini App static files (HTML, JS, CSS). The frontend calls the Cloud Function API via `VITE_API_URL`. CORS is already configured on the API side.

---

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Node.js ≥ 18 and npm
- Python 3.12 with dependencies installed (`pip install -r requirements.txt`)
- `.env.yaml` filled in (see `.env.yaml.example`)

---

## 1. Deploy Cloud Function (bot + API)

```bash
gcloud functions deploy expense-bot \
  --gen2 \
  --runtime=python312 \
  --region=asia-southeast1 \
  --source=. \
  --entry-point=webhook \
  --trigger-http \
  --allow-unauthenticated \
  --env-vars-file=.env.yaml \
  --memory=256MB \
  --timeout=60s \
  --service-account=expense-bot-sa@expense-bot-489609.iam.gserviceaccount.com
```

After deploy, set the webhook:

```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot"
```

---

## 2. Deploy Mini App to GCS

### 2.1 One-time setup

Create `mini-app/.env.production` with the Cloud Function URL:

```
VITE_API_URL=https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot
```

Vite loads this file automatically when building in production mode.

### 2.2 Deploy

Run the deploy script from the project root:

```bash
./deploy_mini_app.sh
```

By default the bucket is named `expense-bot-mini-app`. Pass a custom name if needed:

```bash
./deploy_mini_app.sh my-bucket-name
```

The script performs the following steps:
1. `npm ci` — install dependencies
2. `npm run build` — build the React app (uses `.env.production`)
3. Create the GCS bucket if it doesn't exist (region `asia-southeast1`)
4. Configure the bucket for static website hosting (`index.html` as both main and error page)
5. Grant public read access (`allUsers:objectViewer`)
6. Upload `dist/*` with appropriate cache headers

### 2.3 Configure BotFather

Set the Mini App URL in Telegram:

1. Open [@BotFather](https://t.me/BotFather)
2. `/mybots` → select your bot → **Bot Menu Button**
3. Set URL to: `https://storage.googleapis.com/expense-bot-mini-app/index.html`

---

## 3. Verify

```bash
# API health check
curl -s https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot/api/settings \
  -H "Authorization: tma test" | head -c 200

# Mini App is accessible
curl -sI https://storage.googleapis.com/expense-bot-mini-app/index.html | head -5
```

Open the Mini App via the bot's menu button in Telegram to confirm everything works end-to-end.

---

## Updating

| What changed | Command |
|---|---|
| Bot code or API | Re-deploy Cloud Function (step 1) |
| Mini App frontend | `./deploy_mini_app.sh` (step 2) |
| Both | Run both commands — they are independent |
| Cron schedule or secret | Update job via `gcloud scheduler jobs update http` |

---

## 4. Cloud Scheduler (Recurring Expenses)

### 4.1 One-time setup

Add `CRON_SECRET` to `.env.yaml` (any strong secret string), then redeploy the function:

```bash
./deploy.sh
```

Enable the API if not yet done:

```bash
gcloud services enable cloudscheduler.googleapis.com --project=expense-bot-489609
```

### 4.2 Create the job

```bash
gcloud scheduler jobs create http expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1 \
  --schedule="0 9 * * *" \
  --uri="https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot/cron/recurring" \
  --http-method=POST \
  --headers="X-Cron-Secret=your-strong-secret-here" \
  --time-zone="Asia/Singapore" \
  --attempt-deadline=5m
```

`0 9 * * *` — daily at 09:00 in the specified timezone.

### 4.3 Verify

```bash
# Force a run
gcloud scheduler jobs run expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1

# Check logs
gcloud functions logs read expense-bot \
  --project=expense-bot-489609 \
  --region=asia-southeast1 \
  --limit=50
```

Expected log line: `Recurring cron complete: {'users': N, 'inserted': N, 'skipped': N, 'errors': 0}`

### 4.4 Manage

```bash
gcloud scheduler jobs pause expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs resume expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs delete expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
```

---

## Troubleshooting

### CORS errors in browser console

The API already returns `Access-Control-Allow-Origin: *`. If you see CORS errors:
- Verify the `VITE_API_URL` in `.env.production` points to the correct Cloud Function URL
- Rebuild and re-deploy the Mini App

### Mini App shows blank page

- Check browser console (Telegram Desktop → right-click → Inspect)
- Verify `index.html` is accessible: `curl https://storage.googleapis.com/<bucket>/index.html`
- Ensure the GCS bucket has public access: `gsutil iam get gs://<bucket>`

### API returns 401 Unauthorized

- The Mini App must be opened from Telegram (it needs `initData` for authentication)
- Verify `TELEGRAM_BOT_TOKEN` in `.env.yaml` matches the bot that owns the Mini App
