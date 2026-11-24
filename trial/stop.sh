#!/bin/bash
# Stop Circularity. Your data is kept; start.sh brings it back as you left it.
. "$(dirname "$0")/lib.sh"
need_docker
compose down
say "Stopped. Your data is kept."