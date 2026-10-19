# syntax=docker/dockerfile:1

FROM node:20-alpine AS builder
WORKDIR /app
# `npm ci` は package-lock.json 必須なので glob の `*` は付けない。
# lockfile が無ければ COPY 時点で失敗させ、意図しないフォールバックを防ぐ。
COPY --chown=node:node package.json package-lock.json ./
# `npm install` は semver range を解決し直すため、同じコミットから
# 異なる依存バージョンでイメージが作られうる。`npm ci` は lockfile に
# 完全一致した依存ツリーをインストールし、CI (frontend-ci.yml) と
# 同じ再現性を Docker ビルドにも持ち込む。
RUN npm ci
COPY --chown=node:node . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
# Next.js は起動時に `.next/cache` に fetch キャッシュを書き込むため、
# `--chown=node:node` で node ユーザから書き込み可能な所有権にする。
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/package.json .

# CIS Docker Benchmark 4.1 準拠: プリセットの非 root ユーザで実行
USER node

EXPOSE 3000
CMD ["npm", "run", "start"]
