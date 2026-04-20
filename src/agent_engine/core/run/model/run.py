from dataclasses import dataclass
from datetime import datetime

from agent_engine.core.run.model.resume_handle import ResumeHandle


@dataclass(frozen=True)
class Run:
    run_id: str
    cwd: str
    provider: str
    model: str | None
    resume_handle: ResumeHandle | None
    resume_key: str | None
    created_at: datetime
