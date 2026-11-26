#!/bin/bash
# Build the trial package for customers (trial/START-HERE.md is what they read).
# Packages the COMMITTED HEAD (git archive: uncommitted changes are never included), builds the runtime images from
# it (docker-compose.prod.yml's targets, tagged circularity-trial-*:<version>), saves them with postgres:16-alpine
# into images.tar.gz, and assembles:
#   dist/circularity-trial-<version>/       compose.yml, start/stop/reset/status/uninstall (.sh, .ps1, .cmd),
#                                           START-HERE.md, VERSION, postgres-init/, data/golden/, guides/, images.tar.gz
#   dist/circularity-trial-<version>.tar.gz and .zip
# <version> is <yyyy.mm.dd>-<short sha> (TRIAL_VERSION overrides it). Then run scripts/trial/check.sh on it.
# The host needs git, docker (Compose v2) and tar; the zip is made with Python inside the api image.
set -u
set -o pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
g() { git -c safe.directory="$REPO" -C "$REPO" "$@"; }
sha=$(g rev-parse --short HEAD) || { echo "FAIL  $REPO is not a git checkout" >&2; exit 1; }
VERSION=${TRIAL_VERSION:-$(date -u +%Y.%m.%d)-$sha}
NAME=circularity-trial-$VERSION
DIST="$REPO/dist"
OUT="$DIST/$NAME"

fail() { echo "FAIL  $*" >&2; exit 1; }
pass() { echo "OK    $*"; }

[ -n "$(g status --porcelain -- trial scripts/trial)" ] && echo "WARN  trial/ or scripts/trial/ has uncommitted changes; the package uses HEAD's"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/circtrial-build.XXXXXX") || exit 1
trap 'rm -rf "$TMP"' EXIT
SRC="$TMP/src"
mkdir -p "$SRC"

echo "== export HEAD $sha"
g archive --format=tar HEAD | tar -x -C "$SRC" || fail "git archive"
[ -f "$SRC/trial/compose.yml" ] || fail "trial/compose.yml is not committed at HEAD"

echo "== build the runtime images ($VERSION)"
cat >"$TMP/trial-images.yml" <<EOF
services:
  source-sim: { image: "circularity-trial-source-sim:$VERSION" }
  api: { image: "circularity-trial-api:$VERSION" }
  worker: { image: "circularity-trial-api:$VERSION" }
  web: { image: "circularity-trial-web:$VERSION" }
EOF
(cd "$SRC" && COMPOSE_PROJECT_NAME=circtrialbuild docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f "$TMP/trial-images.yml" build source-sim api web) || fail "docker compose build"
pass "images built"
docker image inspect postgres:16-alpine >/dev/null 2>&1 || docker pull postgres:16-alpine || fail "docker pull postgres:16-alpine"

echo "== assemble $OUT"
rm -rf "$OUT" "$DIST/$NAME.tar.gz" "$DIST/$NAME.zip"
mkdir -p "$OUT/data" "$OUT/guides"
cp "$SRC"/trial/*.sh "$SRC"/trial/*.ps1 "$SRC"/trial/*.cmd "$SRC/trial/START-HERE.md" "$OUT/" || fail "copy scripts"
sed "s/__VERSION__/$VERSION/g" "$SRC/trial/compose.yml" >"$OUT/compose.yml"
grep -q __VERSION__ "$OUT/compose.yml" && fail "compose.yml still has __VERSION__"
printf '%s\n' "$VERSION" >"$OUT/VERSION"
cp -R "$SRC/infra/postgres/init" "$OUT/postgres-init"
cp -R "$SRC/fixtures/golden" "$OUT/data/golden"
cp -R "$SRC/docs/guides/." "$OUT/guides/"
chmod +x "$OUT"/*.sh
for f in $(cd "$OUT" && ls -A); do
  case $f in .env | .env.*) fail "a .env file is in the package" ;; esac
done

echo "== save the images"
docker save "circularity-trial-api:$VERSION" "circularity-trial-web:$VERSION" \
  "circularity-trial-source-sim:$VERSION" postgres:16-alpine | gzip -1 >"$OUT/images.tar.gz" || fail "docker save"
pass "images.tar.gz $(du -h "$OUT/images.tar.gz" | cut -f1)"

echo "== archives"
(cd "$DIST" && tar -czf "$NAME.tar.gz" "$NAME") || fail "tar"
# MSYS_NO_PATHCONV is scoped to this one call: Git Bash would rewrite "-w /d" to "D:/"; other systems ignore it.
MSYS_NO_PATHCONV=1 docker run --rm --user "$(id -u):$(id -g)" -v "$DIST:/d" -w /d --entrypoint python "circularity-trial-api:$VERSION" \
  -m zipfile -c "$NAME.zip" "$NAME" || fail "zip"
pass "$DIST/$NAME.tar.gz ($(du -h "$DIST/$NAME.tar.gz" | cut -f1)), $DIST/$NAME.zip ($(du -h "$DIST/$NAME.zip" | cut -f1))"
echo "== trial package $VERSION built; check it with: bash scripts/trial/check.sh $DIST/$NAME.tar.gz"
