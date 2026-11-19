#!/bin/bash
# Uzum tovar kuzatuvi — Google Cloud Run'ga joylash (bepul limit ichida).
# Google Cloud Shell'da ishga tushiring:
#   curl -fsSL https://raw.githubusercontent.com/cgenki1207/Aziz-uzum/main/deploy-gcp.sh | bash
set -euo pipefail

SERVICE="uzum-tracker"
REGION="us-central1"          # bepul limit AQSh hududlarida
IMAGE="docker.io/library/python:3.12-slim"
BOOT="https://raw.githubusercontent.com/cgenki1207/Aziz-uzum/main/boot.py"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ask() { local v; read -r -p "$1" v </dev/tty; printf '%s' "$v"; }
ask_secret() { local v; read -r -s -p "$1" v </dev/tty; echo >/dev/tty; printf '%s' "$v"; }

# 1. Loyiha
PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [ -z "$PROJECT" ]; then
  say "Google Cloud loyihasi tanlanmagan. Mavjud loyihalar:"
  gcloud projects list --format="value(projectId)"
  PROJECT="$(ask 'Loyiha ID sini yozing (yangi yaratish uchun Enter): ')"
  if [ -z "$PROJECT" ]; then
    PROJECT="uzum-tracker-$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    gcloud projects create "$PROJECT" --name="Uzum tracker"
  fi
  gcloud config set project "$PROJECT" >/dev/null
fi
say "Loyiha: $PROJECT"

# 2. To'lov hisobi (Cloud Run bepul bo'lsa ham Google uni ulashni talab qiladi)
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' 2>/dev/null || true)"
if [ -z "$BILLING" ]; then
  ACCOUNTS="$(gcloud billing accounts list --filter=open=true --format='value(name)')"
  if [ "$(printf '%s\n' "$ACCOUNTS" | grep -c .)" = "1" ]; then
    ACC="${ACCOUNTS#billingAccounts/}"
    BILLING="billingAccounts/$ACC"
    gcloud billing projects link "$PROJECT" --billing-account="$ACC" >/dev/null
  else
    say "To'lov hisobi (Billing account) topilmadi yoki bir nechta."
    echo "console.cloud.google.com/billing sahifasida loyihaga to'lov hisobini ulang va skriptni qayta ishga tushiring."
    exit 1
  fi
fi

say "Kerakli xizmat yoqilmoqda (1–2 daqiqa)…"
gcloud services enable run.googleapis.com

# 3. Sozlamalar
EXISTS=""
gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1 && EXISTS=1
KEEP=""; [ -n "$EXISTS" ] && KEEP=" (o'zgartirmaslik uchun Enter)"

NEW_TOKEN=""; NEW_PW=""
while :; do
  TOKEN="$(ask_secret "Uzum Seller API kaliti$KEEP: ")"
  TOKEN="${TOKEN//[[:space:]]/}"; TOKEN="${TOKEN#Bearer}"; TOKEN="${TOKEN#bearer}"
  if [ -z "$TOKEN" ] && [ -n "$EXISTS" ]; then break; fi
  [ ${#TOKEN} -ge 10 ] && { NEW_TOKEN="$TOKEN"; break; }
  echo "Kalit juda qisqa, qayta kiriting."
done
while :; do
  PW="$(ask_secret "Panel uchun parol o'ylab toping, kamida 8 belgi$KEEP: ")"
  if [ -z "$PW" ] && [ -n "$EXISTS" ]; then break; fi
  if [ ${#PW} -lt 8 ]; then echo "Kamida 8 belgi bo'lsin."; continue; fi
  PW2="$(ask_secret "Parolni yana bir marta: ")"
  [ "$PW" = "$PW2" ] && { NEW_PW="$PW"; break; }
  echo "Parollar bir xil emas, qayta kiriting."
done

# Muhit o'zgaruvchilari faylga yoziladi (parolda har qanday belgi bo'lishi mumkin); eski qiymatlar saqlanadi
umask 077
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
[ -n "$EXISTS" ] && gcloud run services describe "$SERVICE" --region "$REGION" --format=json > "$WORK/old.json"
NEW_TOKEN="$NEW_TOKEN" NEW_PW="$NEW_PW" python3 - "$WORK" <<'PYEOF'
import json, os, secrets, sys, time
work = sys.argv[1]
env = {}
try:
    svc = json.load(open(os.path.join(work, "old.json")))
    for e in svc["spec"]["template"]["spec"]["containers"][0].get("env", []):
        if "value" in e:
            env[e["name"]] = e["value"]
except (OSError, ValueError, KeyError, IndexError):
    pass
env.update(UZUM_SERVER="1", UZUM_NO_BROWSER="1", UZUM_TRACKER_HOME="/tmp/uzum",
           DEPLOYED_AT=str(int(time.time())))        # har safar yangi versiya — eng yangi kod olinadi
env.setdefault("SESSION_SECRET", secrets.token_hex(32))
if os.environ["NEW_TOKEN"]:
    env["UZUM_API_TOKEN"] = os.environ["NEW_TOKEN"]
if os.environ["NEW_PW"]:
    env["APP_PASSWORD"] = os.environ["NEW_PW"]
for k in ("UZUM_API_TOKEN", "APP_PASSWORD"):
    if not env.get(k):
        sys.exit(f"{k} topilmadi — skriptni qayta ishga tushirib, qiymatni kiriting.")
with open(os.path.join(work, "env.yaml"), "w") as f:
    for k, v in env.items():
        f.write(f"{k}: {json.dumps(v)}\n")
PYEOF

say "Cloud Run'ga joylanmoqda…"
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --command python3 \
  --args="^|^-c|import urllib.request as u;exec(u.urlopen('$BOOT').read())" \
  --env-vars-file "$WORK/env.yaml" \
  --cpu 1 --memory 512Mi \
  --min-instances 0 --max-instances 1 --concurrency 40 --timeout 60 \
  --cpu-throttling \
  --allow-unauthenticated \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

# 4. Xavfsizlik uchun: $1 lik byudjet ogohlantirishi (pul yechila boshlasa email keladi)
if [ -n "$BILLING" ] && ! gcloud billing budgets list --billing-account="${BILLING#billingAccounts/}" \
     --format='value(displayName)' 2>/dev/null | grep -qx "Uzum tracker"; then
  gcloud services enable billingbudgets.googleapis.com >/dev/null 2>&1 || true
  gcloud billing budgets create --billing-account="${BILLING#billingAccounts/}" \
    --display-name="Uzum tracker" --budget-amount=1USD \
    --threshold-rule=percent=0.01 --threshold-rule=percent=0.5 --threshold-rule=percent=1.0 >/dev/null 2>&1 \
    && echo "Byudjet ogohlantirishi o'rnatildi: hisobingizdan pul yechila boshlasa emailga xabar keladi." \
    || echo "Byudjet ogohlantirishini o'rnatib bo'lmadi — uni console.cloud.google.com/billing/budgets da qo'lda qo'shing."
fi

say "Tayyor! Panel manzili:"
echo "  $URL"
echo
echo "Birinchi ochilishda Uzumdan ma'lumot yuklanadi (2–3 daqiqa). Sahifani yopmay kuting."
