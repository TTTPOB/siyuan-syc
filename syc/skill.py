"""Install and track the bundled user-level skill, following j-cli's setup model."""

import errno
import hashlib
import json
import os
import re
import shutil
import tempfile
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

import click

_MARKER = ".syc-managed.json"
_SOURCE = "siyuan-syc:syc"


class SkillConflict(click.ClickException):
    """The target contains content syc must not overwrite or remove."""


def skill_target(host: str) -> Path:
    home = Path.home()
    if host == "codex":
        root = (
            Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser().resolve()
        )
    elif host == "claude":
        root = home / ".claude"
    elif host == "dsh":
        root = (
            Path(os.environ.get("DSH_AGENTS_HOME") or home / ".agents")
            .expanduser()
            .resolve()
        )
    else:
        root = home / ".agents"
    return root / "skills" / "syc"


def _skill_resource() -> Traversable:
    return resources.files("syc").joinpath("skills", "syc")


def _load_resource_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}

    def visit(directory: Traversable, prefix: str = "") -> None:
        for child in directory.iterdir():
            name = prefix + child.name
            if child.is_dir():
                visit(child, name + "/")
            elif child.is_file():
                files[name] = child.read_bytes()

    try:
        visit(_skill_resource())
    except OSError as exc:
        raise click.ClickException(
            f"Bundled syc skill is missing or unreadable: {exc}"
        ) from None
    if "SKILL.md" not in files:
        raise click.ClickException("Bundled syc skill has no SKILL.md")
    return files


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _marker_bytes(hashes: dict[str, str]) -> bytes:
    marker = {"schema": 1, "source": _SOURCE, "files": hashes}
    return (json.dumps(marker, indent=2, sort_keys=True) + "\n").encode()


def _managed_files(target: Path) -> dict[str, str] | None:
    if target.is_symlink():
        raise SkillConflict(f"Skill target is a symbolic link: {target}")
    if not target.exists():
        return None
    if not target.is_dir():
        raise SkillConflict(f"Skill target is not a directory: {target}")
    for path in target.rglob("*"):
        if path.is_symlink():
            raise SkillConflict(f"Skill target contains a symbolic link: {path}")
    marker_path = target / _MARKER
    if not marker_path.is_file():
        raise SkillConflict(f"Skill target is not managed by syc: {target}")
    invalid = SkillConflict(f"Managed skill marker is invalid: {marker_path}")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise invalid from None
    if (
        not isinstance(marker, dict)
        or marker.get("schema") != 1
        or marker.get("source") != _SOURCE
    ):
        raise invalid
    files = marker.get("files")
    if not isinstance(files, dict) or "SKILL.md" not in files:
        raise invalid
    for name, digest in files.items():
        if (
            name == _MARKER
            or "\\" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise invalid
        path = target / name
        if not path.is_file() or _hash(path.read_bytes()) != digest:
            raise SkillConflict(f"Managed skill file was modified or removed: {path}")
    return files


def _require_directory_ancestor(target: Path) -> None:
    for parent in target.parents:
        if parent.exists():
            if not parent.is_dir():
                raise SkillConflict(
                    f"Skill target ancestor is not a directory: {parent}"
                )
            return


def _check_new_paths(target: Path, old: dict[str, str], new: dict[str, str]) -> None:
    for name in new.keys() - old.keys():
        path = target / name
        if path.exists():
            raise SkillConflict(
                f"Skill update would replace an unmanaged entry: {path}"
            )
        for parent in path.relative_to(target).parents:
            candidate = target / parent
            if candidate.exists() and not candidate.is_dir():
                raise SkillConflict(
                    f"Skill update requires replacing a non-directory entry: {candidate}"
                )


def _write_tree(target: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _remove_tree(target: Path) -> bool:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()
    else:
        return False
    return True


def _rmdir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError as exc:
        if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
            raise


def _remove_files(target: Path, names: set[str]) -> None:
    parents: set[Path] = set()
    for name in names:
        relative = Path(name)
        (target / relative).unlink()
        parents.update(parent for parent in relative.parents if parent != Path("."))
    for parent in sorted(parents, key=lambda path: len(path.parts), reverse=True):
        _rmdir_if_empty(target / parent)


def install_skill(target: Path, *, force: bool = False) -> bool:
    files = _load_resource_files()
    new = {name: _hash(content) for name, content in files.items()}
    _require_directory_ancestor(target)
    old = None if force else _managed_files(target)
    if old is not None:
        _check_new_paths(target, old, new)
        if old == new:
            return False
        files = {name: files[name] for name in new if old.get(name) != new[name]}
    files[_MARKER] = _marker_bytes(new)

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{target.name}.", dir=target.parent
    ) as temp:
        staged = Path(temp) / target.name
        _write_tree(staged, files)
        if old is None:
            if force:
                _remove_tree(target)
            staged.replace(target)
        else:
            for name in files:
                if name != _MARKER:
                    path = target / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    (staged / name).replace(path)
            _remove_files(target, old.keys() - new.keys())
            (staged / _MARKER).replace(target / _MARKER)
    return True


def remove_skill(target: Path, *, force: bool = False) -> bool:
    # Like j-cli, removal is limited to files proven to belong to the package.
    _require_directory_ancestor(target)
    old = _managed_files(target)
    if old is None:
        return False
    _remove_files(target, set(old) | {_MARKER})
    _rmdir_if_empty(target)
    return True
