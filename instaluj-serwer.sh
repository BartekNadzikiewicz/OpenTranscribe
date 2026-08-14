#!/bin/bash
# Instalacja od zera na serwerze z Dockerem (root lub user w grupie docker).
# Jedno przejscie: sprawdza zasoby -> generuje .env z sekretami -> pyta
# o klucz ElevenLabs -> startuje stack. Idempotentny: istniejacego .env
# nie nadpisuje. Uzycie: ./instaluj-serwer.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/4 Srodowisko =="
docker --version || { echo "BLAD: brak dockera"; exit 1; }
docker compose version || { echo "BLAD: brak docker compose v2"; exit 1; }
docker info >/dev/null 2>&1 || { echo "BLAD: brak dostepu do demona Dockera"; \
  echo "  fix: sudo usermod -aG docker \$USER  + ponowne zalogowanie"; exit 1; }
echo "CPU: $(nproc), RAM: $(free -h | awk 'NR==2{print $2" (wolne "$7")"}')"
df -h . | tail -1
echo "Cel ze spec par.13: 8 CPU / 16 GB RAM / 50+ GB dysku."
read -r -p "Zasoby wystarczaja? [t/N] " ok
[ "${ok:-n}" = "t" ] || { echo "Przerwano."; exit 1; }

echo "== 2/4 Plik .env =="
if [ -f .env ]; then
  echo ".env juz istnieje - zostawiam bez zmian."
else
  cp .env.example .env && chmod 600 .env
  for k in POSTGRES_PASSWORD MINIO_ROOT_PASSWORD REDIS_PASSWORD OPENSEARCH_PASSWORD; do
    sed -i "s|$k=.*|$k=$(openssl rand -hex 32)|g" .env
  done
  sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$(openssl rand -hex 64)|g" .env
  sed -i "s|ENCRYPTION_KEY=.*|ENCRYPTION_KEY=opentranscribe_$(openssl rand -base64 48)|g" .env
  sed -i "s|FLOWER_PASSWORD=.*|FLOWER_PASSWORD=$(openssl rand -hex 16)|g" .env
  sed -i "s|MINIO_KMS_SECRET_KEY=.*|MINIO_KMS_SECRET_KEY=opentranscribe-key:$(openssl rand -base64 32)|g" .env
  sed -i "s|^ASR_PROVIDER=.*|ASR_PROVIDER=elevenlabs|" .env
  sed -i "s|^DEPLOYMENT_MODE=.*|DEPLOYMENT_MODE=lite|" .env
  sed -i "s|^BACKEND_LITE_IMAGE=.*|BACKEND_LITE_IMAGE=ghcr.io/barteknadzikiewicz/opentranscribe-backend-lite:latest|" .env
  printf 'ELEVENLABS_MODEL=scribe_v2\nCAPABILITY_OVERRIDES=chat.rag=false,chat.ungrounded=false\n' >> .env
  read -r -s -p "Klucz API ElevenLabs (pisanie niewidoczne): " K
  echo
  printf 'ELEVENLABS_API_KEY=%s\n' "$K" >> .env
  unset K
  if grep -q CHANGE_ME .env; then echo "BLAD: w .env zostaly CHANGE_ME"; exit 1; fi
  echo ".env wygenerowany (sekrety losowe, klucz zapisany, chmod 600)."
fi

echo "== 3/4 Start stacka =="
./start-serwer.sh

echo "== 4/4 Nastepne kroki =="
echo "Status:  ./start-serwer.sh status"
echo "Haslo bootstrap (konto admin@example.com, jednorazowo w logu):"
echo "  docker logs opentranscribe-backend 2>&1 | grep -i 'GENERATED password'"
echo "UI: http://ADRES_SERWERA:5173  |  po wejsciu: zmiana hasla, potem"
echo "Settings->ASR->Test connection, Settings->Authentication->LDAP."
