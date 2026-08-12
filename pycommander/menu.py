"""The menu model: YAML in, a tree of MenuNode out.

A node is a *section* if it has `items`, a *script* if it has `file`. Nothing
else distinguishes them — there is no type tag to keep in sync.

Validation collects every problem it finds instead of raising on the first one,
so a hand-edited menu file reports all of its mistakes in one pass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

# How a script is launched. The names describe what happens to the window.
LAUNCH_DETACHED = "detached"  # no window at all; output discarded
LAUNCH_TERMINAL = "terminal"  # new window, closes when the script exits
LAUNCH_HOLD = "hold"  # new window, held open until the user presses Enter
LAUNCH_MODES = (LAUNCH_DETACHED, LAUNCH_TERMINAL, LAUNCH_HOLD)
DEFAULT_LAUNCH = LAUNCH_TERMINAL

SECTION_KEYS = {"name", "icon", "items"}
SCRIPT_KEYS = {"name", "icon", "file", "launch", "cwd"}


@dataclass
class MenuNode:
    """One menu entry: either a section with children or a launchable script."""

    name: str
    icon: str | None = None
    file: str | None = None
    launch: str = DEFAULT_LAUNCH
    cwd: str | None = None
    children: list["MenuNode"] = field(default_factory=list)

    @property
    def is_section(self) -> bool:
        return self.file is None

    @property
    def resolved_file(self) -> str | None:
        """The script path with ~ and $VARs expanded and symlinks followed."""
        if self.file is None:
            return None
        return _expand(self.file)

    @property
    def resolved_cwd(self) -> str | None:
        """Working directory for the launch: `cwd` if given, else the script's own."""
        if self.file is None:
            return None
        if self.cwd:
            return _expand(self.cwd)
        return os.path.dirname(self.resolved_file)


def _expand(path: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(path)))


class MenuError(Exception):
    """A menu file that could not be read or parsed at all."""


def load_menu(path: str) -> tuple[list[MenuNode], list[str]]:
    """Read `path` and return (top-level nodes, validation errors).

    Errors are human-readable strings carrying the offending node's location,
    e.g. "menu[2].items[0]: unknown launch mode 'bogus'". A non-empty error
    list means the returned tree is incomplete and should not be used.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise MenuError(f"Menu file not found: {path}") from None
    except OSError as exc:
        raise MenuError(f"Could not read {path}: {exc}") from None
    except yaml.YAMLError as exc:
        raise MenuError(f"{path} is not valid YAML:\n\n{exc}") from None

    errors: list[str] = []

    if data is None:
        return [], ["The menu file is empty; it needs a top-level 'menu:' list."]
    if not isinstance(data, dict):
        return [], ["The menu file must be a mapping with a top-level 'menu:' key."]
    if "menu" not in data:
        return [], ["Missing top-level 'menu:' key."]

    nodes = _parse_list(data["menu"], "menu", errors)
    return nodes, errors


def _parse_list(raw, where: str, errors: list[str]) -> list[MenuNode]:
    if not isinstance(raw, list):
        errors.append(f"{where}: expected a list of items, got {_kind(raw)}.")
        return []
    if not raw:
        errors.append(f"{where}: is empty; a section needs at least one item.")
        return []
    return [
        node
        for i, entry in enumerate(raw)
        if (node := _parse_node(entry, f"{where}[{i}]", errors)) is not None
    ]


def _parse_node(raw, where: str, errors: list[str]) -> MenuNode | None:
    if not isinstance(raw, dict):
        errors.append(f"{where}: expected a mapping with a 'name:', got {_kind(raw)}.")
        return None

    name = raw.get("name")
    if name is None:
        errors.append(f"{where}: missing required 'name:'.")
        name = "(unnamed)"
    elif not isinstance(name, str):
        errors.append(f"{where}: 'name:' must be text, got {_kind(name)}.")
        name = str(name)

    label = f"{where} ({name})"
    has_items = "items" in raw
    has_file = "file" in raw

    if has_items and has_file:
        errors.append(
            f"{label}: has both 'items:' and 'file:' — an item is either a "
            f"section (items) or a script (file), not both."
        )
        return None
    if not has_items and not has_file:
        errors.append(
            f"{label}: has neither 'items:' nor 'file:' — add 'items:' to make "
            f"it a section or 'file:' to make it a launchable script."
        )
        return None

    icon = raw.get("icon")
    if icon is not None and not isinstance(icon, str):
        errors.append(f"{label}: 'icon:' must be text, got {_kind(icon)}.")
        icon = None

    allowed = SECTION_KEYS if has_items else SCRIPT_KEYS
    for key in sorted(set(raw) - allowed):
        kind = "section" if has_items else "script"
        errors.append(f"{label}: '{key}:' is not valid on a {kind}; allowed keys are {_join(allowed)}.")

    if has_items:
        children = _parse_list(raw["items"], f"{where}.items", errors)
        return MenuNode(name=name, icon=icon, children=children)

    file = raw["file"]
    if not isinstance(file, str) or not file.strip():
        errors.append(f"{label}: 'file:' must be a non-empty path, got {_kind(file)}.")
        return None

    launch = raw.get("launch", DEFAULT_LAUNCH)
    if not isinstance(launch, str) or launch not in LAUNCH_MODES:
        errors.append(
            f"{label}: unknown launch mode {launch!r}; expected one of {_join(LAUNCH_MODES)}."
        )
        launch = DEFAULT_LAUNCH

    cwd = raw.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        errors.append(f"{label}: 'cwd:' must be text, got {_kind(cwd)}.")
        cwd = None

    return MenuNode(name=name, icon=icon, file=file, launch=launch, cwd=cwd)


def _kind(value) -> str:
    if value is None:
        return "nothing"
    return {
        bool: "a true/false value",
        int: "a number",
        float: "a number",
        str: "text",
        list: "a list",
        dict: "a mapping",
    }.get(type(value), type(value).__name__)


def _join(values) -> str:
    return ", ".join(sorted(values))
