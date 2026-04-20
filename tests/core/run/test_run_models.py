from datetime import datetime, timezone

from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run import Run
from agent_engine.core.run.model.run_result import RunResult


def test_resume_handle_is_frozen():
    handle = ResumeHandle(provider="claude", session_id="abc")
    try:
        handle.provider = "codex"
    except Exception:
        pass
    assert handle.provider == "claude"


def test_run_is_hashable():
    run = Run(
        run_id="r1",
        cwd="/tmp",
        provider="claude",
        model="sonnet",
        resume_handle=None,
        resume_key=None,
        created_at=datetime.now(timezone.utc),
    )
    assert hash(run) == hash(run)


def test_run_result_default_no_error():
    result = RunResult(
        run_id="r1",
        success=True,
        summary="done",
        error=None,
        duration_ms=10,
        cost_usd=0.0,
        turns=1,
        resume_handle=ResumeHandle(provider="claude", session_id="s1"),
    )
    assert result.success
    assert result.resume_handle is not None
    assert result.resume_handle.session_id == "s1"
