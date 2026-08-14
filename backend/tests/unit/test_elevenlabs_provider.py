"""Unit tests for the ElevenLabs Scribe provider's response mapping."""

from app.services.asr.elevenlabs_provider import ElevenLabsProvider


def _provider() -> ElevenLabsProvider:
    return ElevenLabsProvider(api_key="test-key")


DIARIZED_TOKENS = [
    {"text": "Dzień", "start": 0.1, "end": 0.4, "type": "word", "speaker_id": "speaker_0"},
    {"text": " ", "start": 0.4, "end": 0.45, "type": "spacing", "speaker_id": "speaker_0"},
    {"text": "dobry.", "start": 0.45, "end": 0.9, "type": "word", "speaker_id": "speaker_0"},
    {"text": " ", "start": 0.9, "end": 1.0, "type": "spacing", "speaker_id": "speaker_0"},
    {"text": "Witam", "start": 1.0, "end": 1.4, "type": "word", "speaker_id": "speaker_1"},
    {"text": " ", "start": 1.4, "end": 1.45, "type": "spacing", "speaker_id": "speaker_1"},
    {"text": "serdecznie.", "start": 1.45, "end": 2.1, "type": "word", "speaker_id": "speaker_1"},
]


def test_speaker_change_starts_new_segment():
    segments = _provider()._words_to_segments(DIARIZED_TOKENS)
    assert len(segments) == 2
    assert segments[0].text == "Dzień dobry."
    assert segments[0].speaker == "SPEAKER_00"
    assert segments[0].start == 0.1
    assert segments[0].end == 0.9
    assert segments[1].text == "Witam serdecznie."
    assert segments[1].speaker == "SPEAKER_01"


def test_words_carry_timestamps_and_exclude_spacing():
    segments = _provider()._words_to_segments(DIARIZED_TOKENS)
    assert [w.word for w in segments[0].words] == ["Dzień", "dobry."]
    assert segments[0].words[0].start == 0.1
    assert segments[0].words[1].end == 0.9


def test_long_pause_splits_segment_same_speaker():
    tokens = [
        {"text": "Raz.", "start": 0.0, "end": 0.5, "type": "word", "speaker_id": "speaker_0"},
        {"text": "Dwa.", "start": 5.0, "end": 5.5, "type": "word", "speaker_id": "speaker_0"},
    ]
    segments = _provider()._words_to_segments(tokens)
    assert len(segments) == 2
    assert segments[0].text == "Raz."
    assert segments[1].start == 5.0


def test_no_diarization_yields_single_speakerless_segment():
    tokens = [
        {"text": "Dzień", "start": 0.1, "end": 0.4, "type": "word"},
        {"text": " ", "start": 0.4, "end": 0.45, "type": "spacing"},
        {"text": "dobry.", "start": 0.45, "end": 0.9, "type": "word"},
    ]
    segments = _provider()._words_to_segments(tokens)
    assert len(segments) == 1
    assert segments[0].speaker is None
    assert segments[0].text == "Dzień dobry."


def test_empty_token_stream_yields_no_segments():
    assert _provider()._words_to_segments([]) == []


def test_panel_validation_knows_every_catalog_provider():
    """Regresja 2026-08-14: provider byl w fabryce, ale panelowa walidacja
    (enum schematu + _VALID_PROVIDERS) go nie znala -> HTTP 422 z formularza.
    Kazdy provider z katalogu fabryki musi byc znany obu warstwom."""
    from app.api.endpoints.asr_settings import _VALID_PROVIDERS
    from app.schemas.asr_settings import ASRProvider
    from app.services.asr.factory import ASR_PROVIDER_CATALOG

    for provider_id in ASR_PROVIDER_CATALOG:
        assert provider_id in _VALID_PROVIDERS, f"{provider_id} brak w _VALID_PROVIDERS"
        ASRProvider(provider_id)  # ValueError, gdy brak w enumie schematu
