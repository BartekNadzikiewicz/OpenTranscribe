"""ElevenLabs Scribe ASR provider.

Targets the ElevenLabs Speech-to-Text batch API (REST, no SDK dependency —
uses requests). Diarization (up to 32 speakers) and word-level timestamps are
built into the single synchronous endpoint; there is no upload/poll cycle.

The response carries a flat ``words`` array (tokens typed ``word`` /
``spacing`` / ``audio_event``, each with ``start``/``end`` and, when
diarization is on, ``speaker_id``). Segments are not provided by the API, so
this provider groups words into segments on speaker change, long silence, or
segment length.

``base_url`` is configurable for EU data-residency endpoints and for pointing
tests at a mock server.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

from .base import ASRProvider
from .types import ASRConfig
from .types import ASRResult
from .types import ASRSegment
from .types import ASRWord

logger = logging.getLogger(__name__)

# Segment-building thresholds: a new segment starts on speaker change, on a
# pause longer than _MAX_GAP_SECS, or when the segment already spans
# _MAX_SEGMENT_SECS. Values chosen to match subtitle-friendly segment sizes
# produced by the other cloud providers.
_MAX_GAP_SECS = 1.5
_MAX_SEGMENT_SECS = 30.0


class ElevenLabsProvider(ASRProvider):
    _DEFAULT_BASE = "https://api.elevenlabs.io"

    def __init__(
        self,
        api_key: str,
        model_name: str = "scribe_v2",
        base_url: str | None = None,
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._base = (base_url or self._DEFAULT_BASE).rstrip("/")

    @property
    def provider_name(self) -> str:
        return "elevenlabs"

    def supports_diarization(self) -> bool:
        return True

    def supports_vocabulary(self) -> bool:
        return False

    def supports_translation(self) -> bool:
        return False

    def _hdr(self) -> dict:
        return {"xi-api-key": self._api_key}

    def _err_detail(self, exc: Exception) -> str:
        """Sanitized error including the API response body for HTTP errors."""
        detail = str(exc)
        resp = getattr(exc, "response", None)
        if resp is not None:
            try:
                body = resp.text.strip()
            except Exception:  # noqa: BLE001
                body = ""
            if body:
                detail = f"{detail} — {body[:500]}"
        return self._sanitize_error(detail, self._api_key)

    def validate_connection(self) -> tuple[bool, str, float]:
        """Test the API key against the lightweight /v1/user endpoint."""
        start = time.time()
        try:
            import requests
        except ImportError:
            return False, "requests not installed. Run: pip install requests", 0.0
        try:
            r = requests.get(f"{self._base}/v1/user", headers=self._hdr(), timeout=10)
            ms = (time.time() - start) * 1000
            if r.status_code == 401:
                return False, "Invalid ElevenLabs API key", ms
            return True, f"ElevenLabs reachable (HTTP {r.status_code})", ms
        except Exception as e:
            ms = (time.time() - start) * 1000
            return False, self._sanitize_error(str(e), self._api_key), ms

    def transcribe(
        self,
        audio_path: str,
        config: ASRConfig,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> ASRResult:
        import mimetypes

        import requests

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        filename = os.path.basename(audio_path)
        t_start = time.time()
        logger.info(
            "ElevenLabs transcribe start: file=%s model=%s diarize=%s lang=%s",
            filename,
            self._model_name,
            config.enable_diarization,
            config.language,
        )

        data: dict = {
            "model_id": self._model_name,
            "diarize": "true" if config.enable_diarization else "false",
            "timestamps_granularity": "word",
            "tag_audio_events": "false",
        }
        if config.language and config.language != "auto":
            data["language_code"] = config.language
        if config.enable_diarization and config.num_speakers:
            data["num_speakers"] = str(min(config.num_speakers, 32))

        if progress_callback:
            progress_callback(0.1, "Uploading to ElevenLabs…")

        try:
            content_type = mimetypes.guess_type(audio_path)[0] or "application/octet-stream"
            with open(audio_path, "rb") as f:
                # Single synchronous call: ElevenLabs transcribes during the
                # request, so the read timeout must cover the whole job
                # (files up to 10 h are split into 4 parallel chunks
                # server-side; 2 h of wall clock is a generous ceiling).
                r = requests.post(
                    f"{self._base}/v1/speech-to-text",
                    headers=self._hdr(),
                    files={"file": (filename, f, content_type)},
                    data=data,
                    timeout=(30, 7200),
                )
            r.raise_for_status()
        except Exception as exc:
            sanitized = self._err_detail(exc)
            logger.error("ElevenLabs transcription failed for file=%s: %s", filename, sanitized)
            raise RuntimeError(f"ElevenLabs transcription failed: {sanitized}") from exc

        payload = r.json()
        elapsed_ms = (time.time() - t_start) * 1000
        logger.info(
            "ElevenLabs transcribe complete: file=%s duration_ms=%.0f", filename, elapsed_ms
        )

        if progress_callback:
            progress_callback(0.9, "Parsing ElevenLabs results…")

        segments = self._words_to_segments(payload.get("words") or [])
        if not segments and payload.get("text"):
            # Fallback: no word timing data (e.g. timestamps disabled upstream).
            segments = [ASRSegment(text=payload["text"].strip(), start=0.0, end=0.0)]

        if progress_callback:
            progress_callback(1.0, "ElevenLabs transcription complete")

        return ASRResult(
            segments=segments,
            language=payload.get("language_code") or config.language,
            has_speakers=config.enable_diarization and any(s.speaker for s in segments),
            provider_name="elevenlabs",
            model_name=self._model_name,
            metadata={"language_probability": payload.get("language_probability")},
        )

    def _words_to_segments(self, tokens: list[dict]) -> list[ASRSegment]:
        """Group the flat token stream into speaker/pause/length-bounded segments."""
        segments: list[ASRSegment] = []
        cur_text: list[str] = []
        cur_words: list[ASRWord] = []
        cur_speaker: str | None = None
        cur_start: float | None = None
        cur_end = 0.0

        def flush() -> None:
            nonlocal cur_text, cur_words, cur_start
            text = "".join(cur_text).strip()
            if text:
                segments.append(
                    ASRSegment(
                        text=text,
                        start=cur_start or 0.0,
                        end=cur_end,
                        speaker=cur_speaker,
                        words=cur_words,
                    )
                )
            cur_text, cur_words, cur_start = [], [], None

        for tok in tokens:
            kind = tok.get("type", "word")
            if kind == "spacing":
                # Spacing carries no speaker/timing signal; glue to current segment.
                cur_text.append(tok.get("text", " "))
                continue
            if kind == "audio_event":
                # Non-verbal events (only present when tag_audio_events=true).
                cur_text.append(tok.get("text", ""))
                continue

            start = float(tok.get("start", 0.0))
            end = float(tok.get("end", start))
            speaker = self._normalize_speaker_label(tok.get("speaker_id"))

            boundary = cur_start is not None and (
                speaker != cur_speaker
                or start - cur_end > _MAX_GAP_SECS
                or end - cur_start > _MAX_SEGMENT_SECS
            )
            if boundary:
                flush()
            if cur_start is None:
                cur_start = start
                cur_speaker = speaker

            word_text = tok.get("text", "")
            cur_text.append(word_text)
            cur_words.append(ASRWord(word_text, start, end, 1.0))
            cur_end = end

        flush()
        return segments
