#!/bin/bash
# Reset Circularity to the starting demo data: deletes everything you changed, then starts again.
. "$(dirname "$0")/lib.sh"
need_docker
if [ "${1:-}" != "--yes" ]; then
  printf 'This deletes all changes and starts from the demo data again. Type yes to go on: '
  read -r answer
  [ "$answer" = yes ] || { echo "Nothing changed."; exit 0; }
fi
compose down -v
load_images
write_env
wait_ready