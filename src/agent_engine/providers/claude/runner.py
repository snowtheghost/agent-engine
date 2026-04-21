import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
)

from agent_engine.core.run.model.resume_handle import ResumeHandle
from agent_engine.core.run.model.run_result import RunResult
from agent_engine.providers.claude.mcp_discovery import discover_mcps
from agent_engine.providers.claude.process_manager import ProcessManager
from agent_engine.providers.claude.retry_policy import RetryAction, RetryPolicy
from agent_engine.providers.claude.sdk_process import (
    get_child_pids,
    get_sdk_process_pid,
    resilient_receive,
    wait_for_children,
)
from agent_engine.providers.claude.session_rollback import rollback_session
from agent_engine.providers.claude.session_state_tracker import SessionStateTracker
from agent_engine.providers.claude.token import ensure_token_fresh
from agent_engine.providers.claude.tool_detail import extract_tool_detail

logger = structlog.get_logger(__name__)

PROVIDER_NAME = "claude"
_SUMMARY_TAIL_COUNT = 3
_LOG_PREVIEW_LENGTH = 200
_DISALLOWED_BUILTIN_TOOLS: list[str] = ["Task", "Agent"]


async def _allow_all(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow:
    return PermissionResultAllow()


def _build_time_context(timezone: str) -> str:
    now = datetime.now(ZoneInfo(timezone))
    time_str = now.strftime(f"%I:%M %p {now.tzname()} on %A, %B %d, %Y")
    return f"[Current time: {time_str}]"


@dataclass
class _SessionState:
    session_id: str | None
    result_text: str | None
    is_error: bool
    total_cost_usd: float
    turns: int
    task_completed: bool
    final_text_parts: list[str]
    result_subtype: str | None
    stop_reason: str | None
    used_task_tool: bool


def _build_error_summary(state: _SessionState) -> str:
    if state.result_text:
        return state.result_text
    parts: list[str] = []
    if state.result_subtype:
        parts.append(f"subtype={state.result_subtype}")
    if state.stop_reason:
        parts.append(f"stop_reason={state.stop_reason}")
    if state.final_text_parts:
        parts.append(f"last_output={state.final_text_parts[-1][:500]}")
    if parts:
        return f"Agent error: {'; '.join(parts)}"
    return "Agent reported an error (no details available)"


def _build_run_result(
    run_id: str,
    state: _SessionState,
    duration_ms: int,
) -> RunResult:
    resume_handle: ResumeHandle | None = None
    if state.session_id is not None:
        resume_handle = ResumeHandle(provider=PROVIDER_NAME, session_id=state.session_id)

    if state.is_error:
        error_summary = _build_error_summary(state)
        logger.error(
            "claude_run_error",
            run_id=run_id,
            duration_ms=duration_ms,
            cost_usd=state.total_cost_usd,
            turns=state.turns,
            session_id=state.session_id,
            error=error_summary,
            result_subtype=state.result_subtype,
            stop_reason=state.stop_reason,
        )
        return RunResult(
            run_id=run_id,
            success=False,
            summary=error_summary,
            error=error_summary,
            duration_ms=duration_ms,
            cost_usd=state.total_cost_usd,
            turns=state.turns,
            resume_handle=resume_handle,
        )

    if state.result_text:
        summary = state.result_text
    elif state.final_text_parts:
        summary = "\n".join(state.final_text_parts[-_SUMMARY_TAIL_COUNT:])
    else:
        summary = ""

    logger.info(
        "claude_run_completed",
        run_id=run_id,
        duration_ms=duration_ms,
        cost_usd=state.total_cost_usd,
        turns=state.turns,
        session_id=state.session_id,
    )
    return RunResult(
        run_id=run_id,
        success=True,
        summary=summary,
        error=None,
        duration_ms=duration_ms,
        cost_usd=state.total_cost_usd,
        turns=state.turns,
        resume_handle=resume_handle,
    )


class ClaudeCodeRunner:
    def __init__(
        self,
        *,
        cwd: str,
        model: str,
        effort: str,
        mcp_servers: dict[str, Any],
        timezone: str,
    ) -> None:
        self._cwd = cwd
        self._model = model
        self._effort = effort
        self._mcp_servers = mcp_servers
        self._timezone = timezone
        self._process_manager = ProcessManager()
        self._state_tracker = SessionStateTracker()
        logger.info(
            "claude_runner_initialized",
            cwd=cwd,
            model=model,
            effort=effort,
            mcp_servers=list(mcp_servers.keys()),
        )

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    def is_running(self, run_id: str) -> bool:
        return self._process_manager.is_running(run_id)

    async def interrupt(self, run_id: str) -> bool:
        return await self._process_manager.interrupt(run_id)

    def active_run_ids(self) -> set[str]:
        return self._process_manager.active_run_ids()

    def _build_mcp_servers(self) -> dict[str, Any]:
        merged: dict[str, Any] = dict(self._mcp_servers)
        discovered = discover_mcps(Path(self._cwd))
        for name, config in discovered.items():
            merged.setdefault(name, config)
        return merged

    def _build_options(
        self,
        *,
        model: str,
        session_id: str | None,
        mcp_servers: dict[str, Any],
    ) -> ClaudeAgentOptions:
        allowed_tools = [f"mcp__{name}" for name in mcp_servers]
        return ClaudeAgentOptions(
            model=model,
            mcp_servers=mcp_servers,
            cwd=self._cwd,
            permission_mode="bypassPermissions",
            can_use_tool=_allow_all,
            setting_sources=["user", "project"],
            resume=session_id,
            allowed_tools=allowed_tools,
            disallowed_tools=_DISALLOWED_BUILTIN_TOOLS,
            stderr=lambda line: logger.debug("cli_stderr", output=line),
            thinking={"type": "adaptive"},
            effort=self._effort,
            skills="all",
        )

    async def _stream_session(
        self,
        client: ClaudeSDKClient,
        initial_session_id: str | None,
        run_id: str,
    ) -> _SessionState:
        state = _SessionState(
            session_id=initial_session_id,
            result_text=None,
            is_error=False,
            total_cost_usd=0.0,
            turns=0,
            task_completed=False,
            final_text_parts=[],
            result_subtype=None,
            stop_reason=None,
            used_task_tool=False,
        )

        async for message in resilient_receive(client):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        state.final_text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name.split("__")[-1] if "__" in block.name else block.name
                        if tool_name in ("Task", "Agent"):
                            state.used_task_tool = True
                        detail = extract_tool_detail(block.name, block.input)
                        logger.info("tool_execution", tool=block.name, detail=detail)
                    elif isinstance(block, ToolResultBlock):
                        preview = str(block.content or "")[:_LOG_PREVIEW_LENGTH]
                        logger.debug(
                            "tool_result",
                            tool_use_id=block.tool_use_id,
                            is_error=block.is_error,
                            content_preview=preview,
                        )
                    elif isinstance(block, ThinkingBlock):
                        logger.debug(
                            "thinking_block",
                            preview=block.thinking[:_LOG_PREVIEW_LENGTH],
                        )
            elif isinstance(message, ResultMessage):
                state.total_cost_usd = message.total_cost_usd
                state.turns = message.num_turns
                state.session_id = message.session_id
                state.result_text = message.result
                state.is_error = message.is_error
                state.result_subtype = message.subtype
                state.stop_reason = message.stop_reason
                state.task_completed = True
                if message.session_id:
                    self._state_tracker.track(run_id, message.session_id)
            elif isinstance(message, SystemMessage):
                if message.subtype == "compact_boundary":
                    logger.info(
                        "context_compacted",
                        run_id=run_id,
                        data=str(message.data)[:_LOG_PREVIEW_LENGTH],
                    )
                else:
                    logger.debug(
                        "system_message",
                        subtype=message.subtype,
                        data=str(message.data)[:_LOG_PREVIEW_LENGTH],
                    )

        if state.used_task_tool:
            pid = get_sdk_process_pid(client)
            if pid:
                children = get_child_pids(pid)
                if children:
                    logger.info("subagents_detected", sdk_pid=pid, child_pids=children)
                    await wait_for_children(pid)

        return state

    async def _run_with_retry(
        self,
        options: ClaudeAgentOptions,
        prompt: str,
        run_id: str,
        resume_session_id: str | None,
        start_time: float,
    ) -> RunResult:
        retry_policy = RetryPolicy()
        if resume_session_id is not None:
            self._state_tracker.track(run_id, resume_session_id)

        while True:
            enriched_prompt = f"{_build_time_context(self._timezone)}\n\n{prompt}"
            task_completed = False
            state: _SessionState | None = None

            try:
                async with ClaudeSDKClient(options=options) as client:
                    if self._process_manager.has_collision(run_id):
                        logger.error("active_client_collision", run_id=run_id)
                        return RunResult(
                            run_id=run_id,
                            success=False,
                            summary="",
                            error="Aborted: run already active",
                            duration_ms=0,
                            cost_usd=0.0,
                            turns=0,
                            resume_handle=(
                                ResumeHandle(provider=PROVIDER_NAME, session_id=resume_session_id)
                                if resume_session_id
                                else None
                            ),
                        )
                    self._process_manager.register(run_id, client)
                    await client.query(enriched_prompt)
                    state = await self._stream_session(client, resume_session_id, run_id)
                    task_completed = state.task_completed
            except BaseExceptionGroup as eg:
                critical = eg.subgroup(
                    lambda e: isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError))
                )
                if task_completed:
                    logger.warning("sdk_teardown_error_suppressed", error=str(eg))
                    if critical is not None:
                        raise critical
                else:
                    logger.error(
                        "sdk_session_crashed",
                        error=str(eg),
                        exceptions=[str(e) for e in eg.exceptions],
                    )
                    raise
            except Exception as inner_error:
                action = retry_policy.evaluate(is_resuming=bool(options.resume))
                if action == RetryAction.REVIVAL_ROLLBACK:
                    self._process_manager.unregister(run_id)
                    assert options.resume is not None
                    rolled_back = rollback_session(self._cwd, options.resume)
                    retry_policy.advance_revival(rolled_back)
                    if rolled_back:
                        logger.warning(
                            "session_revival_rollback",
                            stale_session_id=options.resume,
                            error=str(inner_error)[:_LOG_PREVIEW_LENGTH],
                        )
                        continue
                raise

            assert state is not None

            if state.is_error and self._process_manager.consume_interrupted(run_id):
                state.is_error = False
                state.result_text = None
                logger.info(
                    "interrupt_converted_to_success",
                    run_id=run_id,
                    session_id=state.session_id,
                    original_subtype=state.result_subtype,
                )

            duration_ms = int((time.time() - start_time) * 1000)
            return _build_run_result(run_id, state, duration_ms)

    async def run(
        self,
        prompt: str,
        *,
        run_id: str,
        resume_handle: ResumeHandle | None,
        model: str | None,
    ) -> RunResult:
        start_time = time.time()
        resolved_model = model or self._model
        resume_session_id = resume_handle.session_id if resume_handle else None

        logger.info(
            "claude_run_start",
            run_id=run_id,
            resume_session_id=resume_session_id,
            resuming=resume_session_id is not None,
            model=resolved_model,
        )

        mcp_servers = self._build_mcp_servers()
        options = self._build_options(
            model=resolved_model,
            session_id=resume_session_id,
            mcp_servers=mcp_servers,
        )

        await ensure_token_fresh()

        try:
            return await self._run_with_retry(
                options, prompt, run_id, resume_session_id, start_time
            )
        except Exception as error:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception("claude_run_failed")
            return RunResult(
                run_id=run_id,
                success=False,
                summary="",
                error=str(error),
                duration_ms=duration_ms,
                cost_usd=0.0,
                turns=0,
                resume_handle=(
                    ResumeHandle(provider=PROVIDER_NAME, session_id=resume_session_id)
                    if resume_session_id
                    else None
                ),
            )
        finally:
            self._process_manager.unregister(run_id)
            self._state_tracker.untrack(run_id)
