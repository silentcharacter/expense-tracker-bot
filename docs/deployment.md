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
- Application Default Credentials configured for local dev: `gcloud auth application-default login`
- Node.js ≥ 18 and npm (also needed for the Firestore emulator: `npm install -g firebase-tools`)
- Python 3.12 with dependencies installed (`pip install -r requirements.txt`)
- `.env.yaml` filled in (see `.env.yaml.example`)

---

## 0. Firestore Setup (one-time, if migrating from Sheets)

### 0.1 Enable the API and grant IAM permissions

```bash
# Enable Firestore
gcloud services enable firestore.googleapis.com --project=expense-bot-489609

# Grant the Cloud Function's service account Firestore access
gcloud projects add-iam-policy-binding expense-bot-489609 \
  --member="serviceAccount:expense-bot-sa@expense-bot-489609.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

Create the Firestore database if it doesn't exist yet (choose Native mode):

```bash
gcloud firestore databases create \
  --project=expense-bot-489609 \
  --location=asia-southeast1 \
  --type=firestore-native
```

### 0.2 Deploy composite indexes

```bash
# Only the two-field composite is needed — single-field indexes are created automatically
gcloud firestore indexes composite create \
  --project=expense-bot-489609 \
  --collection-group=transactions \
  --field-config=field-path=timestamp,order=ascending \
  --field-config=field-path=recurring_template_id,order=ascending
```

Alternatively, deploy all indexes from `firestore.indexes.json` using the Firebase CLI:

```bash
firebase deploy --only firestore:indexes --project=expense-bot-489609
```

### 0.3 Migrate data from Sheets to Firestore

```bash
# Dry run first — logs what would be written without touching Firestore
python scripts/migrate_sheets_to_firestore.py --dry-run

# Real migration (idempotent — safe to re-run)
python scripts/migrate_sheets_to_firestore.py
```

### 0.4 Add STORAGE_BACKEND to .env.yaml

```yaml
STORAGE_BACKEND: firestore
```

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
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://expense-bot-bsjaw727mq-as.a.run.app"
```

---

## 2. Deploy Mini App to GCS

### 2.1 One-time setup

Create `mini-app/.env.production` with the Cloud Function URL:

```
VITE_API_URL=https://expense-bot-bsjaw727mq-as.a.run.app
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

Replace `<CRON_SECRET>` with the value from `.env.yaml`. Use **single quotes** around the `--headers` value — double quotes cause zsh to interpret `!` and `&` as special characters.

```bash
gcloud scheduler jobs create http expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1 \
  --schedule='0 9 * * *' \
  --uri='https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot/cron/recurring' \
  --http-method=POST \
  --headers='X-Cron-Secret=<CRON_SECRET>' \
  --time-zone='Asia/Singapore' \
  --attempt-deadline=5m
```

`0 9 * * *` — daily at 09:00 in the specified timezone.

### 4.3 Update the secret (if mismatched)

If the job was created with the wrong secret, update it (always use single quotes):

```bash
gcloud scheduler jobs update http expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1 \
  --update-headers='X-Cron-Secret=<CRON_SECRET>'
```

Check the current job config to verify:

```bash
gcloud scheduler jobs describe expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1
```

The `status.code` field must be absent (success) or `0` after the next run. Code `7` means PERMISSION_DENIED — secret mismatch.

### 4.4 Verify

```bash
# Force a run
gcloud scheduler jobs run expense-bot-recurring \
  --project=expense-bot-489609 \
  --location=asia-southeast1

# Check logs (Cloud Functions 2nd gen uses structured logging — no textPayload filter needed)
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="expense-bot"' \
  --project=expense-bot-489609 \
  --limit=30 \
  --format='value(timestamp, jsonPayload.message)'

# Or quick smoke-test via curl
curl -s -X POST \
  'https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot/cron/recurring' \
  -H 'X-Cron-Secret: <CRON_SECRET>' | python3 -m json.tool
```

Expected response: `{"errors": 0, "inserted": N, "skipped": N, "users": N}`

Expected log line: `Recurring cron complete: {'users': N, 'inserted': N, 'skipped': N, 'errors': 0}`

### 4.5 Manage

```bash
gcloud scheduler jobs pause expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs resume expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs delete expense-bot-recurring --project=expense-bot-489609 --location=asia-southeast1
```

---

## 5. Cloud Scheduler (Weekly Summary)

Sends a weekly spending summary to all opted-in users every Monday at 10:00 Asia/Singapore time.

### 5.1 Create the job

Use **single quotes** around `--headers` (see note in section 4.2).

```bash
gcloud scheduler jobs create http expense-bot-weekly-summary \
  --project=expense-bot-489609 \
  --location=asia-southeast1 \
  --schedule='0 10 * * 1' \
  --uri='https://asia-southeast1-expense-bot-489609.cloudfunctions.net/expense-bot/cron/weekly_summary' \
  --http-method=POST \
  --headers='X-Cron-Secret=<CRON_SECRET>' \
  --time-zone='Asia/Singapore' \
  --attempt-deadline=5m
```

`CRON_SECRET` must be set in `.env.yaml` and match the `X-Cron-Secret` header value (same secret used by the recurring job).

### 5.2 Verify

```bash
# Force a run
gcloud scheduler jobs run expense-bot-weekly-summary \
  --project=expense-bot-489609 \
  --location=asia-southeast1

# Check logs
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="expense-bot"' \
  --project=expense-bot-489609 \
  --limit=30 \
  --format='value(timestamp, jsonPayload.message)'
```

Expected log line: `Weekly summary cron complete: {'sent': N, 'skipped': N, 'errors': 0}`

Users with `weekly_summary: false` in their settings (configurable via `/api/settings`) are skipped. Users with no transactions in the previous week are also skipped.

### 5.3 Manage

```bash
gcloud scheduler jobs pause expense-bot-weekly-summary --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs resume expense-bot-weekly-summary --project=expense-bot-489609 --location=asia-southeast1
gcloud scheduler jobs delete expense-bot-weekly-summary --project=expense-bot-489609 --location=asia-southeast1
```

---

## Manual data access (Firestore mode)

- **Firebase Console** — browse/edit user documents at `console.firebase.google.com` → Firestore → `users/{telegram_id}/transactions`
- **Dump to CSV locally** — `python scripts/dump_user.py <telegram_id> --out-dir ./dump`
- **Export via bot** — `/export` command or `GET /api/export` still works as before

---

## Troubleshooting

### Google TLS / ECDSA certificate email (Q2 2026)

Google is rotating some endpoints (including `googleapis.com`) to ECDSA certs via GTS WE1.
**No action needed** for this project: the Mini App uses the browser trust store, Cloud
Functions use the default container CA bundle, and there is no certificate pinning in the
code. The email applies only if you maintain a **custom trust store** or **pin** certs.

### `cloudfunctions.net` returns 503 but `run.app` works

Gen2 functions have two URLs. If `asia-southeast1-….cloudfunctions.net/expense-bot`
returns 503 while `expense-bot-….a.run.app` returns 200/204, point `VITE_API_URL` and
the Telegram webhook at the **run.app** URL (see `gcloud functions describe …
--format='value(serviceConfig.uri)'`).

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
