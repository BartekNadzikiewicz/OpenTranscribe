"""Dispatch-time guards for LLM-backed downstream work.

With no LLM provider configured, LLM tasks (summarization, topic extraction,
speaker identification) must not be queued at all. Deciding in the worker was
not enough: a queued task whose worker never runs it left files with
summary_status='pending' — shown to the user as an eternal "waiting for
summary". The dispatch site runs on the CPU pipeline, which demonstrably works
wherever transcription completes.
"""

import contextlib
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def no_llm(monkeypatch):
    """LLM unconfigured at the shared checkpoint."""
    import app.services.llm_service as llm_module

    monkeypatch.setattr(llm_module.LLMService, "create_from_settings", staticmethod(lambda user_id=None: None))


@pytest.fixture
def llm_present(monkeypatch):
    service = MagicMock()
    import app.services.llm_service as llm_module

    monkeypatch.setattr(
        llm_module.LLMService, "create_from_settings", staticmethod(lambda user_id=None: service)
    )
    return service


def test_is_llm_configured_false_when_unconfigured(no_llm):
    from app.services.llm_service import is_llm_configured

    assert is_llm_configured(user_id=1) is False


def test_is_llm_configured_true_and_closes_probe(llm_present):
    from app.services.llm_service import is_llm_configured

    assert is_llm_configured(user_id=1) is True
    llm_present.close.assert_called_once()


def _fake_media_file():
    mf = MagicMock()
    mf.summary_status = "pending"
    mf.user_id = 1
    return mf


def test_summary_not_queued_without_llm(monkeypatch, no_llm):
    import app.tasks.transcription.downstream as ds

    mf = _fake_media_file()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = mf
    monkeypatch.setattr(ds, "session_scope", lambda: contextlib.nullcontext(db))

    summarization_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "app.tasks.summarization", summarization_mod)
    import app.utils.summary_settings as sset

    monkeypatch.setattr(sset, "get_summary_disable_reason", lambda _db, _uid: None)

    ds._dispatch_automatic_summary(file_id=1, file_uuid="u-1", collection_prompt_uuid=None)

    summarization_mod.summarize_transcript_task.delay.assert_not_called()
    assert mf.summary_status == "not_configured"
    db.commit.assert_called()


def test_summary_queued_with_llm(monkeypatch, llm_present):
    import app.tasks.transcription.downstream as ds

    mf = _fake_media_file()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = mf
    monkeypatch.setattr(ds, "session_scope", lambda: contextlib.nullcontext(db))

    summarization_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "app.tasks.summarization", summarization_mod)
    import app.utils.summary_settings as sset

    monkeypatch.setattr(sset, "get_summary_disable_reason", lambda _db, _uid: None)

    ds._dispatch_automatic_summary(file_id=1, file_uuid="u-1", collection_prompt_uuid=None)

    summarization_mod.summarize_transcript_task.delay.assert_called_once()
    assert mf.summary_status == "pending"


def test_topic_extraction_not_queued_without_llm(monkeypatch, no_llm):
    import app.tasks.transcription.downstream as ds

    monkeypatch.setattr(ds, "_file_owner_id", lambda _fid: 1)
    topics_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "app.tasks.topic_extraction", topics_mod)

    ds.trigger_automatic_summarization(file_id=1, file_uuid="u-1", tasks_to_run=["topic_extraction"])

    topics_mod.extract_topics_task.delay.assert_not_called()


def test_speaker_llm_not_queued_without_llm(monkeypatch, no_llm):
    import app.tasks.speaker_attribute_task as sat

    row = MagicMock()
    row.__getitem__ = lambda _self, _i: 1
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = row

    import app.db.session_utils as su

    monkeypatch.setattr(su, "session_scope", lambda: contextlib.nullcontext(db))
    speaker_tasks_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "app.tasks.speaker_tasks", speaker_tasks_mod)

    sat._dispatch_llm_speaker_identification("u-1")

    speaker_tasks_mod.identify_speakers_llm_task.delay.assert_not_called()
