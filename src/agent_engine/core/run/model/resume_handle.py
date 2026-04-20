from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeHandle:
    provider: str
    session_id: str
