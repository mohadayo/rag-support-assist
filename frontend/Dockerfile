# syntax=docker/dockerfile:1

FROM node:20-alpine AS builder
WORKDIR /app
COPY --chown=node:node package.json package-lock.json* ./
RUN npm install
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
