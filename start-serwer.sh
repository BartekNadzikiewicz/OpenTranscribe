#!/bin/bash
# Start/stop na serwerze testowym: obrazy z ghcr.io (fork), tryb lite.
# Uzycie: ./start-serwer.sh            (start)
#         ./start-serwer.sh stop       (stop)
#         ./start-serwer.sh logs backend
set -e
cd "$(dirname "$0")"
# Serwer testowy: male pule procesow (RAM!); te exporty dzialaja,
# bo tutejszy compose podstawia zmienne tylko ze srodowiska powloki.
export CLOUD_ASR_CONCURRENCY=${CLOUD_ASR_CONCURRENCY:-4} CPU_WORKER_CONCURRENCY=${CPU_WORKER_CONCURRENCY:-4} NLP_CONCURRENCY=${NLP_CONCURRENCY:-2} DOWNLOAD_CONCURRENCY=${DOWNLOAD_CONCURRENCY:-2}

PLIKI="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.lite.yml -f docker-compose.ghcr.yml"

# docker compose (z aliasem podman-docker) albo podman compose
if command -v docker >/dev/null 2>&1; then
  KOMPOZYTOR="docker compose"
else
  KOMPOZYTOR="podman compose"
fi

case "${1:-start}" in
  start) $KOMPOZYTOR $PLIKI up -d ;;
  stop)  $KOMPOZYTOR $PLIKI down ;;
  logs)  shift; $KOMPOZYTOR $PLIKI logs -f "$@" ;;
  status) $KOMPOZYTOR $PLIKI ps ;;
  *) echo "uzycie: $0 [start|stop|logs <serwis>|status]"; exit 2 ;;
esac
