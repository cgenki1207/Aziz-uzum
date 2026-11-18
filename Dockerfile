# Uzum tovar kuzatuvi — server uchun.
# Kerakli muhit o'zgaruvchilari:
#   APP_PASSWORD    — panelga kirish paroli (kamida 8 belgi)
#   UZUM_API_TOKEN  — Uzum Seller API kaliti (ixtiyoriy: panelning o'zida ham kiritish mumkin)
#   PORT            — tinglash porti (hosting o'zi beradi, standart 8080)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UZUM_SERVER=1 UZUM_NO_BROWSER=1 UZUM_TRACKER_HOME=/data PORT=8080
WORKDIR /app
COPY run.py ./
COPY uzum_tracker ./uzum_tracker
RUN useradd -r -u 10001 app && mkdir -p /data && chown app /data
USER app
EXPOSE 8080
CMD ["python", "run.py", "--no-browser"]
