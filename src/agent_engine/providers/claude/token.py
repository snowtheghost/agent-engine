import asyncio
import json
import os
import time
from pathlib import Path

import claude_agent_sdk
import structlog

logger = structlog.get_logger(__name__)

_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
_CLAUDE_JSON_PATH = Path.home() / ".claude.json"
_REFRESH_BUFFER_SECONDS = 300


def _normalize_expiry(expires_at: int | float) -> float:
    if expires_at > 1e12:
        return expires_at / 1000
    return float(expires_at)


async def ensure_token_fresh() -> bool:
    try:
        if not _CREDENTIALS_PATH.exists():
            if _CLAUDE_JSON_PATH.exists():
                data = json.loads(_CLAUDE_JSON_PATH.read_text())
                if data.get("primaryApiKey"):
                    logger.debug("token_using_managed_api_key")
                    return True
            logger.warning("token_check_no_credentials")
            return False

        data = json.loads(_CREDENTIALS_PATH.read_text())
        oauth = data.get("claudeAiOauth", {})
        expires_at = oauth.get("expiresAt", 0)
        expires_at_seconds = _normalize_expiry(expires_at)

        now = time.time()
        remaining = expires_at_seconds - now

        if remaining > _REFRESH_BUFFER_SECONDS:
            logger.debug("token_still_fresh", remaining_hours=round(remaining / 3600, 2))
            return True

        logger.warning(
            "token_near_expiry_refreshing",
            remaining_seconds=round(remaining),
            expired=remaining <= 0,
        )

        process = await asyncio.create_subprocess_exec(
            str(Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"),
            "auth",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "CLAUDECODE": ""},
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

        if process.returncode == 0:
            data_after = json.loads(_CREDENTIALS_PATH.read_text())
            oauth_after = data_after.get("claudeAiOauth", {})
            new_expires = oauth_after.get("expiresAt", 0)
            new_expires_seconds = _normalize_expiry(new_expires)

            if new_expires_seconds > expires_at_seconds:
                new_remaining = new_expires_seconds - time.time()
                logger.info(
                    "token_refreshed",
                    new_remaining_hours=round(new_remaining / 3600, 2),
                )
                return True

            logger.warning("token_refresh_no_change", stdout=stdout.decode()[:200])
            return remaining > 0

        logger.error(
            "token_refresh_failed",
            returncode=process.returncode,
            stderr=stderr.decode()[:200],
        )
        return remaining > 0

    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("token_check_error", error=str(exc))
        return True
