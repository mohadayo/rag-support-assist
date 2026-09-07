# syntax=docker/dockerfile:1

FROM python:3.12-slim

# CIS Docker Benchmark 4.1 準拠: 非 root ユーザ (UID 1000) を作成
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home /app --shell /sbin/nologin app

WORKDIR /app

# 依存インストールは root のまま実行 (パッケージインストールに書き込み権限が要る)。
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app/ ./app/

# 以降のプロセスは非 root ユーザで実行する。
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
