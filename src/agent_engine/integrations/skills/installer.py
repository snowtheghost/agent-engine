from importlib.resources import files
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_PACKAGE_ROOT = "agent_engine.integrations.skills.bundled"


def install_bundled_skills(cwd: Path) -> list[str]:
    target_root = cwd / ".claude" / "skills"
    target_root.mkdir(parents=True, exist_ok=True)

    installed: list[str] = []
    package = files(_PACKAGE_ROOT)
    for entry in package.iterdir():
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        target_dir = target_root / entry.name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"
        source_text = skill_file.read_text(encoding="utf-8")
        if not target_file.exists() or target_file.read_text(encoding="utf-8") != source_text:
            target_file.write_text(source_text, encoding="utf-8")
            logger.info("skill_installed", name=entry.name, path=str(target_file))
        installed.append(entry.name)
    return installed
