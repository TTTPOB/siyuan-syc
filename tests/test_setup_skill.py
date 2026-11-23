"""Behavior tests adapted from the j-cli skill installer suite."""

import hashlib
import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from syc import skill
from syc.cli import main
from syc.skill import SkillConflict, install_skill, remove_skill


@pytest.fixture
def bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "bundle"
    (source / "workflows").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: syc\n---\n")
    (source / "workflows" / "example.md").write_text("workflow v1\n")
    monkeypatch.setattr(skill, "_skill_resource", lambda: source)
    return source


def test_install_complete_with_hashes_and_idempotent(
    tmp_path: Path, bundled: Path
) -> None:
    target = tmp_path / "agent" / "skills" / "syc"
    assert install_skill(target)
    marker = json.loads((target / ".syc-managed.json").read_text())
    for name in ("SKILL.md", "workflows/example.md"):
        data = (bundled / name).read_bytes()
        assert (target / name).read_bytes() == data
        assert marker["files"][name] == hashlib.sha256(data).hexdigest()
    assert not install_skill(target)


def test_update_removes_obsolete_and_preserves_unrelated_files(
    tmp_path: Path, bundled: Path
) -> None:
    target = tmp_path / "syc"
    assert install_skill(target)
    unrelated = target / "notes.txt"
    unrelated.write_text("keep me")
    (bundled / "workflows" / "example.md").unlink()
    (bundled / "workflows" / "new.md").write_text("workflow v2")
    assert install_skill(target)
    assert not (target / "workflows" / "example.md").exists()
    assert (target / "workflows" / "new.md").read_text() == "workflow v2"
    assert remove_skill(target)
    assert list(target.iterdir()) == [unrelated]
    assert unrelated.read_text() == "keep me"


def test_remove_is_idempotent_for_clean_target(tmp_path: Path, bundled: Path) -> None:
    target = tmp_path / "syc"
    assert not remove_skill(target)
    assert install_skill(target)
    assert remove_skill(target)
    assert not target.exists()
    assert not remove_skill(target)


@pytest.mark.parametrize(
    "kind", ["unmanaged", "modified", "invalid-marker", "file", "link", "dangling"]
)
def test_force_install_replaces_conflicts_but_force_remove_does_not(
    tmp_path: Path, bundled: Path, kind: str
) -> None:
    target = tmp_path / "syc"
    if kind == "unmanaged":
        target.mkdir()
        (target / "old.txt").write_text("unmanaged")
    elif kind in {"modified", "invalid-marker"}:
        assert install_skill(target)
        changed = "SKILL.md" if kind == "modified" else ".syc-managed.json"
        (target / changed).write_text("changed")
    elif kind == "file":
        target.write_text("keep me")
    else:
        source = tmp_path / "linked"
        if kind == "link":
            source.mkdir()
            (source / "keep.txt").write_text("keep me")
        target.symlink_to(source, target_is_directory=True)

    with pytest.raises(SkillConflict):
        install_skill(target)
    with pytest.raises(SkillConflict):
        remove_skill(target, force=True)
    assert install_skill(target, force=True)
    assert not target.is_symlink()
    assert (target / "SKILL.md").read_bytes() == (bundled / "SKILL.md").read_bytes()
    assert not (target / "old.txt").exists()
    if kind == "link":
        assert (tmp_path / "linked" / "keep.txt").read_text() == "keep me"


def test_unmanaged_file_at_new_resource_path_is_preserved(
    tmp_path: Path, bundled: Path
) -> None:
    target = tmp_path / "syc"
    assert install_skill(target)
    user_file = target / "workflows" / "added.md"
    user_file.write_text("local")
    (bundled / "workflows" / "added.md").write_text("packaged")
    with pytest.raises(SkillConflict, match="unmanaged entry"):
        install_skill(target)
    assert user_file.read_text() == "local"


def test_force_resource_failure_preserves_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "syc"
    target.write_text("keep me")
    monkeypatch.setattr(skill, "_skill_resource", lambda: tmp_path / "missing")
    with pytest.raises(click.ClickException, match="missing or unreadable"):
        install_skill(target, force=True)
    assert target.read_text() == "keep me"


def test_force_staging_failure_preserves_existing_target(
    tmp_path: Path, bundled: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "syc"
    target.mkdir()
    (target / "local.txt").write_text("keep me")

    def fail_write(staging: Path, files: dict[str, bytes]) -> None:
        staging.mkdir()
        (staging / "partial.txt").touch()
        raise OSError("disk full")

    monkeypatch.setattr(skill, "_write_tree", fail_write)
    with pytest.raises(OSError, match="disk full"):
        install_skill(target, force=True)
    assert (target / "local.txt").read_text() == "keep me"
    assert not list(tmp_path.glob(".syc.*"))


def test_install_and_remove_reject_file_ancestor(tmp_path: Path, bundled: Path) -> None:
    ancestor = tmp_path / "ancestor"
    ancestor.write_text("keep me")
    target = ancestor / "skills" / "syc"
    for operation in (install_skill, remove_skill):
        with pytest.raises(SkillConflict, match="ancestor is not a directory"):
            operation(target, force=True)
    assert ancestor.read_text() == "keep me"


@pytest.mark.parametrize(
    "host,root_dir",
    [
        ("dsh", "agents-override"),
        ("codex", "codex-override"),
        ("claude", ".claude"),
        ("opencode", ".agents"),
    ],
)
def test_setup_uses_host_user_directory_and_real_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str, root_dir: str
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DSH_AGENTS_HOME", str(tmp_path / "agents-override"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-override"))
    runner = CliRunner()
    result = runner.invoke(main, ["setup", host])
    assert result.exit_code == 0, result.output
    target = tmp_path / root_dir / "skills" / "syc"
    assert json.loads(result.stdout)["path"] == str(target)
    assert (target / "SKILL.md").is_file()
    assert (target / "workflows" / "assets.md").is_file()
    assert runner.invoke(main, ["setup", host, "--remove"]).exit_code == 0
    assert not target.exists()
