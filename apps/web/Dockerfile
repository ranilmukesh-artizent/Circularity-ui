# The web app. Targets:
#   dev      what docker-compose.yml builds: the Vite dev server, the source bind-mounted over /app (port 5173).
#   build    `vite build` into /app/dist.
#   runtime  nginx (unprivileged, port 8080) serving dist with a Content-Security-Policy and proxying /api and /mcp to
#            di-api (nginx/default.conf.template; API_UPSTREAM, default http://api:8000).
# The build reads the demo's stylesheet and product photos from src/styles/legacy.gen.css and public/assets/products,
# which scripts/extract-styles.mjs generates from fixtures/demo (outside this build context) before every dev, build
# and test run. Run `node apps/web/scripts/extract-styles.mjs` (or start the dev server once) before building runtime.
# Base images are pinned by digest: node 24.22.2-alpine3.24 (2026-11-05), nginx-unprivileged 1.30.6-alpine3.24
# (stable, 2026-10-19). All targets build with the classic builder too: `docker build --target runtime apps/web`.
FROM node:24.22.2-alpine3.24@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM deps AS build
COPY . .
RUN test -s src/styles/legacy.gen.css && test -d public/assets/products \
    || { echo "missing generated styles/photos: run node scripts/extract-styles.mjs first" >&2; exit 1; }
# `vite build` without the typecheck (scripts/dev/web-check.sh runs tsc) and without the prebuild hook (the demo is
# not in this context; the generated files above are)
RUN npx vite build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine3.24@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS runtime
ENV API_UPSTREAM=http://api:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
