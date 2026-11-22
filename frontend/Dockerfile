# The web app's dev image: what docker-compose.yml builds (context frontend, target dev). The Vite dev server, the
# source bind-mounted over /app, port 5173; `npm run dev` regenerates the demo's stylesheet and photos from the demo
# mounted at /legacy (scripts/extract-styles.mjs).
# The production image (nginx serving the built app with a CSP) is frontend/Dockerfile.runtime, built from the repo
# root so the demo is in its context (docker-compose.prod.yml).
# Base image pinned by digest: node 24.22.2-alpine3.24 (2026-11-05). Classic-builder compatible:
# `docker build --target dev frontend`.
FROM node:24.22.2-alpine3.24@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
