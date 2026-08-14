# PRZERÓBKI — rejestr naszych odstępstw od upstreamu

Zasada: KAŻDA zmiana względem upstreamu ma tu wpis (co, po co, status
upstream). Aktualizacja OpenTranscribe = rebase naszych commitów na nowy
release TAG + przejście tabeli od góry + testy + smoke E2E.
Cel długofalowy: tabela pusta (wszystko przyjęte upstream) albo bliska
pustej.

| # | Pliki | Co i po co | Status upstream |
|---|-------|-----------|-----------------|
| 1 | `backend/app/services/asr/elevenlabs_provider.py` (NOWY), `factory.py` (4 wpisy), `schemas/asr_settings.py` (enum), `api/endpoints/asr_settings.py` (2 listy), `frontend/src/lib/api/asrSettings.ts` (typ+etykieta), `tests/unit/test_provider_sdk_compat.py` (1 linia), `tests/unit/test_elevenlabs_provider.py` (NOWY, w tym test parzystości katalog↔walidacja panelu) | Provider ElevenLabs Scribe (nasz silnik docelowy): diaryzacja słowo-po-słowie → segmenty, base_url konfigurowalny (EU residency / atrapa). Uzupełnienie 2026-08-14: provider w walidacji PANELU (enum+listy+frontend) — brak powodował HTTP 422 przy „Test connection"; test parzystości pilnuje kompletu na przyszłość | DO ZGŁOSZENIA jako PR — architektura providerów jest na to otwarta (przewodnik w `asr/CLAUDE.md`) |
| 2 | `backend/app/core/capabilities.py` (`_parse_capability_overrides`), `tests/unit/test_capability_overrides.py` (NOWY) | Env `CAPABILITY_OVERRIDES` = wyłączanie powierzchni funkcji w self-hosted (u nas: `chat.rag=false,chat.ungrounded=false`) — chowa czat z UI i 404-uje router | DO ZGŁOSZENIA jako PR — wpisuje się w ich własny opis „server-driven feature gating"; do czasu przyjęcia utrzymujemy lokalnie |
| 3 | `frontend/vite.config.ts` (5 linii) | Targety dev-proxy z env: `VITE_BACKEND_URL` (fallback `backend:8080`) i `VITE_MINIO_URL` (fallback `minio:9000`, w tym nagłówek Host — podpis presigned URL obejmuje hosta) — dev poza Dockerem | DO ZGŁOSZENIA jako PR (czysto addytywne) |
| 4 | `backend/requirements-lite.txt` — dopisane: cachetools, imohash, nltk (wersje jak w pełnym requirements.txt) | Obraz lite NIE WSTAJE bez nich (`main.py`: No module named cachetools) — potwierdzone na serwerze 2026-08-14 na obrazie z CI, wcześniej maskowane ręczną instalacją w venv środowiska testowego | DO ZGŁOSZENIA jako ISSUE/PR — realny błąd upstreamu w obrazie lite |
| 5 | `frontend/src/lib/i18n/locales/pl.json` (NOWY, 4908 kluczy), `frontend/src/lib/i18n/languages.ts` (1 linia) | Polska wersja UI; parity-check upstreamu przechodzi (`npm run check:i18n`) | DO ZGŁOSZENIA jako PR — czysto addytywny, najlepszy kandydat |
| 6 | `frontend/src/assets/logo-banner.png`, `logo-icon.png` (nadpisane, te same nazwy/wymiary) | Neutralne logo zastępcze („Transkrypcja"/„T") zamiast brandingu OpenTranscribe; docelowo logo firmowe. Informacje licencyjne (About/AGPL) pozostają nietknięte. | LOKALNE — celowo nie do upstreamu |
| 7 | `.github/workflows/build-images.yml` (NOWY), `docker-compose.ghcr.yml` (NOWY), `start-serwer.sh` (NOWY), `instaluj-serwer.sh` (NOWY — instalacja jednym przejściem: zasoby → .env z sekretami → klucz → start), `docker-compose.prod.yml` i `docker-compose.lite.yml` (usunięte linie `pull_policy`) | Warstwa wdrożeniowa forka: CI buduje obrazy lite do ghcr.io (paczki publiczne, serwer ciągnie anonimowo); overlay ghcr podmienia obrazy na nasze; skrypt startowy skleja yml+prod+lite+ghcr. `pull_policy: always` upstreamu WYCIĘTE z prod/lite (2026-08-14): każdy start pytał rejestr i wywracał się na niedomagającym DNS serwera („server misbehaving"); nakładka z `pull_policy: missing`/`if_not_present` odpadła, bo compose na serwerze (Podman 5.4.0) jej nie trawi („pull policy not allowed"); bez tej opcji domyślne zachowanie = obraz lokalny, pull tylko gdy brak. Świadomy koszt: aktualizacja obrazów wymaga jawnego `podman pull`. Overlay ghcr wymusza też obraz lite dla serwisów wyłączanych przez `deploy.replicas=0`/profile GPU (`celery-worker`, `celery-worker-gpu-*`): podman-compose ignoruje replicas i ściągał im PEŁNY backend 8,9 GB (incydent 2026-08-14, dysk 15 GB). | LOKALNE — specyficzne dla naszego wdrożenia; przy rebase na nowy tag ponowić wycięcie |
| — | `.env` (lokalny), `PRZEROBKI.md` (ten plik) | konfiguracja instancji; poza gitem upstreamu | nie dotyczy |

## Procedura aktualizacji (kwartalnie + przy release'ach bezpieczeństwa)
1. `git fetch upstream && git log v<stary>..v<nowy>` — przejrzeć changelog,
   szczególnie `asr/`, `capabilities.py`, `vite.config.ts` (nasze punkty styku).
2. Rebase naszej gałęzi `nasze-dostosowania` na nowy tag.
3. Testy: `pytest tests/unit/test_elevenlabs_provider.py
   test_capability_overrides.py test_provider_sdk_compat.py
   test_capability_contract.py` + pełny zestaw upstreamu.
4. Smoke E2E na atrapie: upload → transkrypcja → TXT z mówcami.
5. Wpis w DECYZJE projektu (wersja, co się zmieniło, czy diff zmalał).
