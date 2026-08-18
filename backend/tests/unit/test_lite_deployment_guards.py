"""Tests for lite-deployment guards: no GPU workers → no GPU-queue dispatches.

Lite images ship no local Whisper, no GPU workers, and no speaker-embedding
models, so anything routed to the gpu/cpu-transcribe queues never runs there.
Three surfaces must respect that:

- postprocess must not hand pipeline completion to the async GPU embedding
  task (the file previously sat at 90% "Processing speaker identification"
  until the periodic recovery sweep reclaimed it);
- whisper_model API overrides must be refused up front (the CPU-whisper
  route they trigger cannot run in a lite image);
- the periodic embedding-consistency check must not dispatch GPU repair
  batches (a "Repairing 0 of N" notification that never progresses).
"""

import contextlib
import sys
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

import app.core.config as config_module
from app.core.config import is_lite_deployment
from app.schemas.media import PrepareUploadRequest
from app.schemas.media import ReprocessRequest


@pytest.fixture
def lite(monkeypatch):
    monkeypatch.setattr(config_module.settings, "DEPLOYMENT_MODE", "lite")


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setattr(config_module.settings, "DEPLOYMENT_MODE", "full")


# ---------------------------------------------------------------------------
# is_lite_deployment
# ---------------------------------------------------------------------------


def test_is_lite_deployment_flag(monkeypatch):
    monkeypatch.setattr(config_module.settings, "DEPLOYMENT_MODE", "lite")
    assert is_lite_deployment() is True
    # Tolerates whitespace/case from hand-edited .env files.
    monkeypatch.setattr(config_module.settings, "DEPLOYMENT_MODE", " LITE ")
    assert is_lite_deployment() is True
    monkeypatch.setattr(config_module.settings, "DEPLOYMENT_MODE", "full")
    assert is_lite_deployment() is False


# ---------------------------------------------------------------------------
# whisper_model API refusal (schemas)
# ---------------------------------------------------------------------------


def test_reprocess_rejects_whisper_model_in_lite(lite):
    with pytest.raises(ValidationError, match="unavailable in this deployment"):
        ReprocessRequest(whisper_model="base")


def test_prepare_upload_rejects_whisper_model_in_lite(lite):
    with pytest.raises(ValidationError, match="unavailable in this deployment"):
        PrepareUploadRequest(
            filename="a.mp3", file_size=1, content_type="audio/mpeg", whisper_model="base"
        )


def test_reprocess_allows_default_model_in_lite(lite):
    """None/empty = server-configured engine — always allowed."""
    assert ReprocessRequest(whisper_model=None).whisper_model is None
    assert ReprocessRequest(whisper_model="  ").whisper_model is None


def test_reprocess_allows_whisper_model_in_full(full):
    assert ReprocessRequest(whisper_model="base").whisper_model == "base"


def test_reprocess_still_rejects_unknown_model_in_full(full):
    with pytest.raises(ValidationError, match="Unknown Whisper model"):
        ReprocessRequest(whisper_model="not-a-model")


# ---------------------------------------------------------------------------
# dispatch routing chokepoint (covers internal callers, not just the API)
# ---------------------------------------------------------------------------


def test_cpu_whisper_route_disabled_in_lite(lite):
    from app.tasks.transcription.dispatch import _route_to_cpu_whisper

    assert _route_to_cpu_whisper("base") is False


def test_cpu_whisper_route_enabled_in_full(full):
    from app.tasks.transcription.dispatch import _route_to_cpu_whisper

    assert _route_to_cpu_whisper("base") is True
    assert _route_to_cpu_whisper(None) is False
    assert _route_to_cpu_whisper("large-v3") is False  # heavyweight → GPU route


# ---------------------------------------------------------------------------
# embedding consistency check
# ---------------------------------------------------------------------------


def test_consistency_check_skips_in_lite(lite):
    from app.tasks.speaker_embedding_consistency import (
        speaker_embedding_consistency_check_task,
    )

    result = speaker_embedding_consistency_check_task()
    assert result == {"status": "skipped", "reason": "lite_deployment"}


# ---------------------------------------------------------------------------
# postprocess completion (the 90% hang)
# ---------------------------------------------------------------------------


def _gpu_result() -> dict:
    return {
        "task_id": "task-1",
        "file_uuid": "uuid-1",
        "file_id": 1,
        "user_id": 1,
        "speaker_mapping": {},
        "asr_provider": "elevenlabs",
        "diarization_disabled": False,
        "diarization_source": "provider",
    }


@pytest.fixture
def pp_harness(monkeypatch):
    """finalize_transcription with all side effects stubbed; returns spies."""
    import app.tasks.transcription.postprocess as pp

    spies = {
        "statuses": [],
        "completion": MagicMock(),
        "embedding": MagicMock(),
    }
    monkeypatch.setattr(pp, "session_scope", lambda: contextlib.nullcontext(MagicMock()))
    monkeypatch.setattr(
        pp,
        "update_task_status",
        lambda db, tid, status, **kw: spies["statuses"].append((status, kw)),
    )
    monkeypatch.setattr(pp, "send_progress_notification", MagicMock())
    monkeypatch.setattr(pp, "send_completion_notification", spies["completion"])
    monkeypatch.setattr(pp, "send_ws_event", MagicMock())
    monkeypatch.setattr(pp, "benchmark_timing", MagicMock())
    monkeypatch.setattr(pp, "_fire_completion_metering", MagicMock())
    monkeypatch.setattr(pp, "_build_enrichment_task_list", lambda d: [])
    monkeypatch.setattr(pp, "enrich_and_dispatch", MagicMock())
    monkeypatch.setattr(pp, "_cleanup_temp", MagicMock())
    monkeypatch.setitem(
        sys.modules,
        "app.tasks.speaker_embedding_task",
        MagicMock(extract_speaker_embeddings_task=spies["embedding"]),
    )
    spies["run"] = lambda: pp.finalize_transcription(_gpu_result())
    return spies


def test_lite_cloud_pipeline_completes_without_gpu_embedding(lite, pp_harness):
    """The 90% hang: in lite mode nothing consumes the gpu queue, so the
    pipeline must complete here instead of waiting for the embedding task."""
    pp_harness["run"]()
    pp_harness["embedding"].apply_async.assert_not_called()
    assert ("completed", {"progress": 1.0, "completed": True}) in pp_harness["statuses"]
    pp_harness["completion"].assert_called_once()


def test_full_cloud_pipeline_defers_completion_to_embedding_task(full, pp_harness):
    """Unchanged upstream behavior with GPU workers present."""
    pp_harness["run"]()
    pp_harness["embedding"].apply_async.assert_called_once()
    assert ("in_progress", {"progress": 0.9}) in pp_harness["statuses"]
    assert not any(s == "completed" for s, _ in pp_harness["statuses"])
    pp_harness["completion"].assert_not_called()


def test_full_cloud_pipeline_completes_when_dispatch_fails(full, pp_harness):
    """Pre-existing upstream bug: a failed embedding dispatch left the file
    at 90% forever. It must now fall through to completion."""
    pp_harness["embedding"].apply_async.side_effect = RuntimeError("broker down")
    pp_harness["run"]()
    assert ("completed", {"progress": 1.0, "completed": True}) in pp_harness["statuses"]
    pp_harness["completion"].assert_called_once()


def test_full_cloud_pipeline_honors_extract_embeddings_off(full, pp_harness, monkeypatch):
    """CLOUD_ASR_EXTRACT_EMBEDDINGS existed in config/.env.example but was
    read nowhere — the declared off-switch must actually switch off."""
    monkeypatch.setattr(config_module.settings, "CLOUD_ASR_EXTRACT_EMBEDDINGS", False)
    pp_harness["run"]()
    pp_harness["embedding"].apply_async.assert_not_called()
    assert ("completed", {"progress": 1.0, "completed": True}) in pp_harness["statuses"]
