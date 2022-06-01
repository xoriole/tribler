#!/usr/bin/env bash
docker run -p 52194:52194 \
  -v /home/sysadmin/tudelft/dev/tribler/scripts/experiments/popularity_community/.env:/home/user/tribler/scripts/experiments/popularity_community/.env \
  --net="host" triblercore/triblercore:latest \
  ./scripts/experiments/popularity_community/docker-entrypoint.sh