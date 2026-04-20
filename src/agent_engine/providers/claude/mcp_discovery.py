import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def discover_mcps(cwd: Path) -> dict[str, Any]:
    mcp_dir = cwd / ".mcp"
    configs: dict[str, Any] = {}
    if not mcp_dir.is_dir():
        return configs

    for json_file in sorted(mcp_dir.glob("*.json")):
        try:
            config = json.loads(json_file.read_text())
            configs[json_file.stem] = config
            logger.debug("mcp_discovered", name=json_file.stem, path=str(json_file))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("mcp_config_invalid", path=str(json_file), error=str(exc))

    logger.info("mcp_discovery_complete", servers=list(configs.keys()))
    return configs
