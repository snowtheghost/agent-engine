import structlog

from agent_engine.application.indexing.scheduler import IndexingJob

logger = structlog.get_logger(__name__)


class InlineIndexingScheduler:
    def schedule(self, job: IndexingJob, *, name: str) -> None:
        try:
            job()
        except Exception:
            logger.exception("inline_indexing_job_failed", name=name)
