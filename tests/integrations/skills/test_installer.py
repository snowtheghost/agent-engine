from pathlib import Path

from agent_engine.integrations.skills.installer import install_bundled_skills


def test_install_creates_skill_files(tmp_path: Path):
    names = install_bundled_skills(tmp_path)
    assert {"remember", "recall"}.issubset(set(names))

    for name in names:
        skill_path = tmp_path / ".claude" / "skills" / name / "SKILL.md"
        assert skill_path.is_file()
        content = skill_path.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "description:" in content.splitlines()[1]


def test_install_is_idempotent(tmp_path: Path):
    first = install_bundled_skills(tmp_path)
    second = install_bundled_skills(tmp_path)
    assert first == second


def test_install_rewrites_on_content_change(tmp_path: Path):
    install_bundled_skills(tmp_path)
    skill_file = tmp_path / ".claude" / "skills" / "remember" / "SKILL.md"
    skill_file.write_text("stale", encoding="utf-8")

    install_bundled_skills(tmp_path)
    refreshed = skill_file.read_text(encoding="utf-8")
    assert refreshed != "stale"
    assert refreshed.startswith("---")
