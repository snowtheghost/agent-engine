class SessionStateTracker:

    def __init__(self) -> None:
        self._active_session_ids: dict[str, str] = {}

    def track(self, run_id: str, session_id: str) -> None:
        self._active_session_ids[run_id] = session_id

    def untrack(self, run_id: str) -> None:
        self._active_session_ids.pop(run_id, None)

    def get_active_session_ids(self) -> dict[str, str]:
        return dict(self._active_session_ids)
