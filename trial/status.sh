#!/bin/bash
# Show whether each part of Circularity is running and healthy.
. "$(dirname "$0")/lib.sh"
need_docker
compose ps
[ -f .env ] && echo "App address: http://localhost:$(port)"