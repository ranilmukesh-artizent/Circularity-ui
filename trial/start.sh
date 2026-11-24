#!/bin/bash
# Start Circularity (macOS, Linux, WSL). The first start loads the images and writes .env.
. "$(dirname "$0")/lib.sh"
need_docker
load_images
write_env
wait_ready