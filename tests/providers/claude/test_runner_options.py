from __future__ import annotations

from agent_engine.providers.claude.runner import ClaudeCodeRunner


def _runner() -> ClaudeCodeRunner:
    return ClaudeCodeRunner(
        cwd="/tmp/nonexistent-cwd",
        model="claude-opus-4",
        effort="max",
        mcp_servers={},
        timezone="UTC",
    )


def test_system_prompt_uses_claude_code_preset():
    options = _runner()._build_options(
        model="claude-opus-4",
        session_id=None,
        mcp_servers={},
    )

    assert options.system_prompt == {"type": "preset", "preset": "claude_code"}


def test_setting_sources_includes_user_and_project():
    options = _runner()._build_options(
        model="claude-opus-4",
        session_id=None,
        mcp_servers={},
    )

    assert options.setting_sources == ["user", "project"]


def test_skills_enabled():
    options = _runner()._build_options(
        model="claude-opus-4",
        session_id=None,
        mcp_servers={},
    )

    assert options.skills == "all"


def test_disallowed_tools_contains_task_and_agent():
    options = _runner()._build_options(
        model="claude-opus-4",
        session_id=None,
        mcp_servers={},
    )

    assert "Task" in options.disallowed_tools
    assert "Agent" in options.disallowed_tools
