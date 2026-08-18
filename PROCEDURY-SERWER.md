# Procedury serwerowe — Transkryptor (OpenTranscribe lite)

Katalog aplikacji na serwerze zawiera WYŁĄCZNIE pliki czytane w czasie
działania. Kod aplikacji przyjeżdża w obrazach (ghcr.io), dane mieszkają
w wolumenach nazwanych Dockera — nigdy w tym katalogu.

## Zawartość katalogu (kompletna lista)

```
docker-compose.yml            # definicje serwisów (edytowane: porty, limity)
docker-compose.prod.yml       # tryb produkcyjny
docker-compose.lite.yml       # tryb lite (bez GPU)
docker-compose.ghcr.yml       # nasze obrazy + limity RAM/CPU
start-serwer.sh               # start | stop | logs <serwis> | status
instaluj-serwer.sh            # tylko pierwsza instalacja
PRZEROBKI.md                  # rejestr naszych zmian względem upstreamu
PROCEDURY-SERWER.md           # ten plik
.env                          # sekrety (chmod 600; NIGDY z tarballa)
models/                       # cache modeli ML (bind-mount; w lite ~pusty)
```

## ⚠ Nazwa katalogu = nazwa projektu compose = prefiks WOLUMENÓW z danymi

Zmiana nazwy/lokalizacji katalogu odcina stack od bazy i nagrań.
Zabezpieczenie (jednorazowo): sprawdź prefiks istniejących wolumenów
`docker volume ls | grep postgres_data` i wpisz go do `.env`:
`COMPOSE_PROJECT_NAME=<prefiks>` — od tej pory nazwa katalogu przestaje
mieć znaczenie.

## Wdrożenie nowej wersji

1. Push na fork (komputer prywatny) → poczekać na ZIELONY workflow
   `build-images` (github.com/<fork>/actions).
2. Komputer wdrożeniowy:
   ```bash
   curl -L -o opentranscribe.tar.gz \
     https://github.com/<FORK>/archive/refs/heads/nasze-dostosowania.tar.gz
   scp opentranscribe.tar.gz SERWER:~/
   ```
3. Serwer — zatrzymanie i kopia `.env`:
   ```bash
   cd ~/KATALOG_APLIKACJI && ./start-serwer.sh stop
   cp .env ~/env-kopia-$(date +%F)
   ```
4. Rozpakowanie WYŁĄCZNIE plików serwerowych (reszta 134 MB repo
   celowo zostaje w archiwum):
   ```bash
   tar xzf ~/opentranscribe.tar.gz --strip-components=1 --wildcards \
     '*/docker-compose.yml' '*/docker-compose.prod.yml' \
     '*/docker-compose.lite.yml' '*/docker-compose.ghcr.yml' \
     '*/start-serwer.sh' '*/instaluj-serwer.sh' \
     '*/PRZEROBKI.md' '*/PROCEDURY-SERWER.md'
   ```
5. Nowe obrazy i start:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     -f docker-compose.lite.yml -f docker-compose.ghcr.yml pull
   ./start-serwer.sh && ./start-serwer.sh status
   ```
6. Po potwierdzeniu, że działa — sprzątnięcie starych warstw obrazów:
   ```bash
   docker image prune -f       # bezpieczne: tylko nieotagowane
   ```
   (do tego momentu stary obraz = darmowy rollback: `./start-serwer.sh stop`,
   przywrócić poprzedni kod z tarballa, start BEZ pull)

## Weryfikacja po wdrożeniu

- `./start-serwer.sh status` — wszystkie kontenery Up/healthy;
- upload krótkiego nagrania → 100% bez zawieszenia, TXT do pobrania;
- wyłączone funkcje odmawiają:
  `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5174/api/files/process-url` → 404
  (test bez logowania; konto super_admin celowo OMIJA blokady).

## Rytm operacyjny

- po KAŻDEJ zmianie `.env` → świeża kopia poza serwer (ENCRYPTION_KEY
  jest nieodtwarzalny; jego utrata = dane w bazie nie do odszyfrowania);
- dostęp administracyjny przez tunel SSH:
  `ssh -L 5173:localhost:5173 LOGIN@SERWER` (UI: http://localhost:5173;
  diagnostyka API: dodatkowo `-L 5174:localhost:5174`);
- baza wyłącznie przez `docker exec -it opentranscribe-postgres psql -U postgres opentranscribe`
  (infrastruktura celowo bez portów na hoście);
- kontrola dysku: `docker system df`;
- NIGDY: `docker system prune -a` ani nic z flagą `--volumes`
  (kasuje wolumeny z bazą i nagraniami);
- kwartalnie + przy wydaniach bezpieczeństwa upstreamu: rebase forka
  (procedura w PRZEROBKI.md).
