#!/bin/bash
# Remove Circularity from Docker: the containers, the data and the images. This folder stays; delete it yourself.
. "$(dirname "$0")/lib.sh"
need_docker
if [ "${1:-}" != "--yes" ]; then
  printf 'This deletes the app, its data and its images from Docker. Type yes to go on: '
  read -r answer
  [ "$answer" = yes ] || { echo "Nothing changed."; exit 0; }
fi
compose down -v --remove-orphans
for img in "${IMAGES[@]}"; do docker image rm "$img:$VERSION" >/dev/null 2>&1; done
say "Removed. postgres:16-alpine is left in place in case other projects use it (docker image rm postgres:16-alpine)."