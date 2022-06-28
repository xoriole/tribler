#!/usr/bin/env bash
docker run -p 52194:52194 \
  -v /home/sysadmin/tudelft/dev/tribler/scripts/experiments/common/.env:/home/user/tribler/scripts/experiments/common/.env \
  --net="host" triblercore/experiment:gigachannel \
  ./scripts/experiments/gigachannel_community/docker-entrypoint.sh