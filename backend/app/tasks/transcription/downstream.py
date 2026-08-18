"""Post-transcription downstream task dispatch.

Summarization, topic extraction, analytics, and speaker clustering.
"""

import logging

from app.db.session_utils import session_scope
from app.models.media import MediaFile

logger = logging.getLogger(__name__)


def _dispatch_automatic_summary(
    file_id: int, file_uuid: str, collection_prompt_uuid: str | None
) -> None:
    """Check summary disable settings and dispatch if enabled."""
    from app.tasks.summarization import send_summary_notification
    from app.tasks.summarization import summarize_transcript_task
    from app.utils.summary_settings import get_summary_disable_reason

    with session_scope() as db:
        media_file = db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
        if not media_file:
            logger.warning(f"File {file_uuid} not found for summary dispatch")
            return

        if str(media_file.summary_status) == "disabled":
            logger.info(f"Summary disabled for file {file_id} (per-file flag)")
            send_summary_notification(
                int(media_file.user_id),
                file_id,
                "disabled",
                "AI summary generation is disabled for this file",
                0,
            )
            return

        disable_reason = get_summary_disable_reason(db, int(media_file.user_id))
        if disable_reason:
            media_file.summary_status = "disabled"  # type: ignore[assignment]
            db.commit()
            reason_msg = (
                "AI summary generation has been disabled by the system administrator"
                if disable_reason == "system"
                else "AI summary auto-generation is disabled in your settings"
            )
            logger.info(f"Summary disabled for file {file_id} (reason: {disable_reason})")
            send_summary_notification(
                int(media_file.user_id),
                file_id,
                "disabled",
                reason_msg,
                0,
            )
            return

        # No LLM configured: decide HERE (CPU queue) instead of queueing a task
        # whose worker may not run it — a queued-but-never-run summarization
        # left summary_status='pending', shown as an eternal "waiting for
        # summary". Mirrors _handle_no_llm_configured in the task itself.
        if not _llm_configured(int(media_file.user_id)):
            media_file.summary_status = "not_configured"  # type: ignore[assignment]
            media_file.summary_data = None  # type: ignore[assignment]
            db.commit()
            logger.info(f"No LLM configured — not queueing summarization for file {file_id}")
            return

    summary_task = summarize_transcript_task.delay(
        file_uuid=file_uuid,
        prompt_uuid=collection_prompt_uuid,
    )
    logger.info(f"Automatic summarization task {summary_task.id} started for file {file_id}")


def _llm_configured(user_id: int) -> bool:
    """Dispatch-time LLM configuration check (no health probe)."""
    from app.services.llm_service import is_llm_configured

    return is_llm_configured(user_id=user_id)


def _file_owner_id(file_id: int) -> int | None:
    """Owner user id for a file, or None when the lookup fails."""
    try:
        with session_scope() as db:
            row = db.query(MediaFile.user_id).filter(MediaFile.id == file_id).first()
            return int(row[0]) if row else None
    except Exception as e:
        logger.warning(f"Owner lookup failed for file {file_id}: {e}")
        return None


def _get_collection_prompt_uuid(file_id: int) -> str | None:
    """Look up the default summary prompt UUID from the file's first collection (by added_at)."""
    try:
        from app.db.session_utils import session_scope
        from app.models.media import Collection
        from app.models.media import CollectionMember
        from app.models.prompt import SummaryPrompt

        with session_scope() as db:
            result = (
                db.query(SummaryPrompt.uuid)
                .join(Collection, Collection.default_summary_prompt_id == SummaryPrompt.id)
                .join(CollectionMember, CollectionMember.collection_id == Collection.id)
                .filter(
                    CollectionMember.media_file_id == file_id,
                    SummaryPrompt.is_active,
                )
                .order_by(CollectionMember.added_at.asc())
                .first()
            )

            if result:
                logger.info(f"File {file_id} using collection default prompt: {result[0]}")
                return str(result[0])

        return None
    except Exception as e:
        logger.warning(f"Failed to get collection prompt for file {file_id}: {e}")
        return None


# Import for automatic summarization, speaker identification, and analytics
def trigger_automatic_summarization(
    file_id: int, file_uuid: str, tasks_to_run: list[str] | None = None
):
    """Trigger automatic summarization, speaker identification, and analytics after transcription completes.

    Note: In the default (full) flow, LLM speaker identification is dispatched by
    detect_speaker_attributes_task after gender detection completes, ensuring gender
    data is available to the LLM. When tasks_to_run explicitly includes 'speaker_llm',
    it is dispatched directly for selective reprocessing.

    Args:
        file_id: Internal file ID
        file_uuid: File UUID string
        tasks_to_run: Optional list of specific stages to run. None = run all tasks.
            Valid values: 'analytics', 'speaker_llm', 'summarization',
            'topic_extraction', 'search_indexing', 'speaker_clustering'
    """
    try:
        # Analytics computation
        if tasks_to_run is None or "analytics" in tasks_to_run:
            from app.tasks.analytics import analyze_transcript_task

            analytics_task = analyze_transcript_task.delay(file_uuid=file_uuid)
            logger.info(
                f"Automatic analytics computation task {analytics_task.id} started for file {file_id}"
            )

        # Speaker LLM identification: always chained from detect_speaker_attributes_task
        # (dispatched by _dispatch_speaker_attributes in postprocess). Gender detection
        # runs first, then chains to LLM speaker ID to ensure gender/age context is
        # available. No direct dispatch needed here — would cause double dispatch.

        # Note: search_indexing is dispatched in _process_transcription_result (always
        # runs during transcription). No need to dispatch it here to avoid double dispatch.

        # Look up collection default prompt for this file
        collection_prompt_uuid = _get_collection_prompt_uuid(file_id)

        # Summarization
        if tasks_to_run is None or "summarization" in tasks_to_run:
            _dispatch_automatic_summary(file_id, file_uuid, collection_prompt_uuid)

        # Topic extraction (LLM-backed — same dispatch-time gate as summarization)
        if tasks_to_run is None or "topic_extraction" in tasks_to_run:
            owner_id = _file_owner_id(file_id)
            if owner_id is not None and not _llm_configured(owner_id):
                logger.info(f"No LLM configured — not queueing topic extraction for file {file_id}")
            else:
                from app.tasks.topic_extraction import extract_topics_task

                topic_task = extract_topics_task.delay(file_uuid=file_uuid, force_regenerate=False)
                logger.info(
                    f"Automatic topic extraction task {topic_task.id} started for file {file_id}"
                )

        # Speaker clustering (selective reprocessing only)
        _clustering_stages = {"speaker_clustering"}
        if tasks_to_run is not None and _clustering_stages & set(tasks_to_run):
            try:
                from app.db.session_utils import session_scope
                from app.models.media import MediaFile

                with session_scope() as _db:
                    _mf = _db.query(MediaFile).filter(MediaFile.uuid == file_uuid).first()
                    if not _mf:
                        logger.warning(f"File {file_uuid} not found for clustering dispatch")
                    else:
                        _uid = int(_mf.user_id)

                        if "speaker_clustering" in tasks_to_run:
                            try:
                                from app.tasks.speaker_clustering import cluster_speakers_for_file

                                cluster_speakers_for_file.delay(file_uuid, _uid)
                                logger.info(
                                    f"Selective speaker clustering dispatched for file {file_id}"
                                )
                            except Exception as sc_err:
                                logger.warning(f"Failed to dispatch speaker clustering: {sc_err}")

            except Exception as e:
                logger.warning(f"Failed to look up file for clustering dispatch: {e}")
    except Exception as e:
        logger.warning(f"Failed to start automatic tasks for file {file_id}: {e}")
