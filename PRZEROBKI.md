# PRZERÓBKI — rejestr naszych odstępstw od upstreamu

Zasada: KAŻDA zmiana względem upstreamu ma tu wpis (co, po co, status
upstream). Aktualizacja OpenTranscribe = rebase naszych commitów na nowy
release TAG + przejście tabeli od góry + testy + smoke E2E.
Cel długofalowy: tabela pusta (wszystko przyjęte upstream) albo bliska
pustej.

| # | Pliki | Co i po co | Status upstream |
|---|-------|-----------|-----------------|
| 1 | `backend/app/services/asr/elevenlabs_provider.py` (NOWY), `factory.py` (4 wpisy), `tests/unit/test_provider_sdk_compat.py` (1 linia), `tests/unit/test_elevenlabs_provider.py` (NOWY) | Provider ElevenLabs Scribe (nasz silnik docelowy): diaryzacja słowo-po-słowie → segmenty, base_url konfigurowalny (EU residency / atrapa) | DO ZGŁOSZENIA jako PR — architektura providerów jest na to otwarta (przewodnik w `asr/CLAUDE.md`) |
| 2 | `backend/app/core/capabilities.py` (`_parse_capability_overrides`), `tests/unit/test_capability_overrides.py` (NOWY) | Env `CAPABILITY_OVERRIDES` = wyłączanie powierzchni funkcji w self-hosted (u nas: `chat.rag=false,chat.ungrounded=false`) — chowa czat z UI i 404-uje router | DO ZGŁOSZENIA jako PR — wpisuje się w ich własny opis „server-driven feature gating"; do czasu przyjęcia utrzymujemy lokalnie |
| 3 | `frontend/vite.config.ts` (5 linii) | Targety dev-proxy z env: `VITE_BACKEND_URL` (fallback `backend:8080`) i `VITE_MINIO_URL` (fallback `minio:9000`, w tym nagłówek Host — podpis presigned URL obejmuje hosta) — dev poza Dockerem | DO ZGŁOSZENIA jako PR (czysto addytywne) |
| 4 | `requirements-lite.txt` — braki doinstalowane ręcznie: cachetools, nltk, imohash | Obraz lite nie wstaje natywnie bez nich (w Dockerze maskowane innym obrazem?) | DO ZGŁOSZENIA jako ISSUE (do potwierdzenia na czystym venv) |
| 5 | `frontend/src/lib/i18n/locales/pl.json` (NOWY, 4908 kluczy), `frontend/src/lib/i18n/languages.ts` (1 linia) | Polska wersja UI; parity-check upstreamu przechodzi (`npm run check:i18n`) | DO ZGŁOSZENIA jako PR — czysto addytywny, najlepszy kandydat |
| 6 | `frontend/src/assets/logo-banner.png`, `logo-icon.png` (nadpisane, te same nazwy/wymiary) | Neutralne logo zastępcze („Transkrypcja"/„T") zamiast brandingu OpenTranscribe; docelowo logo firmowe. Informacje licencyjne (About/AGPL) pozostają nietknięte. | LOKALNE — celowo nie do upstreamu |
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
