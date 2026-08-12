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

SECTION_KEYS = {"folder", "icon", "items"}
SCRIPT_KEYS = {"name", "icon", "file", "sh", "launch", "cwd"}
OPTION_KEYS = {"editor"}
TOP_LEVEL_KEYS = {"menu", "options"}


@dataclass
class Options:
    """Top-level settings, from the file's `options:` block."""

    editor: str | None = None

    def resolved_editor(self) -> str:
        """The command that opens the menu file.

        A shell command, so it may carry arguments (`code -n`). Unset falls
        back to the usual environment variables, then to whatever the desktop
        associates with the file.
        """
        return self.editor or os.environ.get("VISUAL") or os.environ.get("EDITOR") or "xdg-open"


@dataclass
class MenuNode:
    """One menu entry: a section with children, or a launchable script.

    A script is either a `file` on disk or an inline `sh` snippet — never both.
    """

    name: str
    icon: str | None = None
    file: str | None = None
    sh: str | None = None
    launch: str = DEFAULT_LAUNCH
    cwd: str | None = None
    children: list["MenuNode"] = field(default_factory=list)

    @property
    def is_section(self) -> bool:
        return self.file is None and self.sh is None

    @property
    def resolved_file(self) -> str | None:
        """The script path with ~ and $VARs expanded and symlinks followed."""
        if self.file is None:
            return None
        return _expand(self.file)

    @property
    def resolved_cwd(self) -> str | None:
        """Working directory: `cwd` if given, else a sensible default.

        A `file` script runs from its own directory, the way Commander ran it.
        An inline `sh` snippet has no directory of its own, so it starts in
        $HOME — the same place a freshly opened terminal would.
        """
        if self.is_section:
            return None
        if self.cwd:
            return _expand(self.cwd)
        if self.file is not None:
            return os.path.dirname(self.resolved_file)
        return os.path.expanduser("~")


def _expand(path: str) -> str:
    return os.path.realpath(os.path.expanduser(os.path.expandvars(path)))


class MenuError(Exception):
    """A menu file that could not be read or parsed at all."""


def load_menu(path: str) -> tuple[list[MenuNode], Options, list[str]]:
    """Read `path` and return (top-level nodes, options, validation errors).

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
    options = Options()

    if data is None:
        return [], options, ["The menu file is empty; it needs a top-level 'menu:' list."]
    if not isinstance(data, dict):
        return [], options, ["The menu file must be a mapping with a top-level 'menu:' key."]
    if "menu" not in data:
        return [], options, ["Missing top-level 'menu:' key."]
    for key in sorted(set(data) - TOP_LEVEL_KEYS):
        errors.append(f"'{key}:' is not a top-level key; expected {_join(TOP_LEVEL_KEYS)}.")

    if "options" in data:
        options = _parse_options(data["options"], errors)
    nodes = _parse_list(data["menu"], "menu", errors)
    return nodes, options, errors


def _parse_options(raw, errors: list[str]) -> Options:
    if not isinstance(raw, dict):
        errors.append(f"options: expected a mapping of settings, got {_kind(raw)}.")
        return Options()

    for key in sorted(set(raw) - OPTION_KEYS):
        errors.append(f"options: '{key}:' is not a setting; expected {_join(OPTION_KEYS)}.")

    editor = raw.get("editor")
    if editor is not None and (not isinstance(editor, str) or not editor.strip()):
        errors.append(f"options: 'editor:' must be a non-empty command, got {_kind(editor)}.")
        editor = None
    return Options(editor=editor)


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
        errors.append(f"{where}: expected a mapping with a 'name:' or 'folder:', got {_kind(raw)}.")
        return None

    has_items = "items" in raw
    has_file = "file" in raw
    has_sh = "sh" in raw

    # A section is named with `folder:`; a script (file or sh) with `name:`.
    name_key = "folder" if has_items else "name"
    name = raw.get(name_key)
    if name is None:
        errors.append(f"{where}: missing required '{name_key}:'.")
        name = "(unnamed)"
    elif not isinstance(name, str):
        errors.append(f"{where}: '{name_key}:' must be text, got {_kind(name)}.")
        name = str(name)

    label = f"{where} ({name})"

    # Exactly one of the three decides what this item is.
    present = [k for k, ok in (("items", has_items), ("file", has_file), ("sh", has_sh)) if ok]
    if len(present) > 1:
        clashing = _join_and([f"'{k}:'" for k in present])
        errors.append(
            f"{label}: has {clashing} together — an item is either a section "
            f"('items:'), a script file ('file:'), or an inline snippet ('sh:'), "
            f"and only one of those."
        )
        return None
    if not present:
        errors.append(
            f"{label}: has none of 'items:', 'file:' or 'sh:' — add 'items:' to make "
            f"it a section, or 'file:'/'sh:' to make it launchable."
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

    file = sh = None
    if has_file:
        file = raw["file"]
        if not isinstance(file, str) or not file.strip():
            errors.append(f"{label}: 'file:' must be a non-empty path, got {_kind(file)}.")
            return None
    else:
        sh = raw["sh"]
        if not isinstance(sh, str) or not sh.strip():
            errors.append(
                f"{label}: 'sh:' must be non-empty shell commands, got {_kind(sh)}."
            )
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

    return MenuNode(name=name, icon=icon, file=file, sh=sh, launch=launch, cwd=cwd)


class _MenuDumper(yaml.SafeDumper):
    """SafeDumper with one addition: multi-line strings dump as `|` blocks.

    Without this, an inline `sh:` snippet with newlines would come back out
    as a quoted string full of literal "\\n"s instead of the readable block
    style the file uses elsewhere.
    """


def _represent_str(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_MenuDumper.add_representer(str, _represent_str)


def _node_to_dict(node: MenuNode) -> dict:
    """The inverse of `_parse_node`: a MenuNode back to a plain dict."""
    if node.is_section:
        d: dict = {"folder": node.name}
        if node.icon:
            d["icon"] = node.icon
        d["items"] = [_node_to_dict(child) for child in node.children]
        return d

    d = {"name": node.name}
    if node.icon:
        d["icon"] = node.icon
    if node.file is not None:
        d["file"] = node.file
    else:
        d["sh"] = node.sh
    if node.launch != DEFAULT_LAUNCH:
        d["launch"] = node.launch
    if node.cwd:
        d["cwd"] = node.cwd
    return d


def dump_menu(path: str, nodes: list[MenuNode], options: Options) -> None:
    """Write `nodes`/`options` back out to `path` as YAML.

    This is a full rewrite from the in-memory tree, not an edit of the
    existing file: it uses plain PyYAML rather than a round-trip-preserving
    library, so any comments or hand-formatting in the current file are lost
    once this runs. That trade-off was made deliberately to avoid a second
    YAML dependency.
    """
    data: dict = {}
    if options.editor:
        data["options"] = {"editor": options.editor}
    data["menu"] = [_node_to_dict(node) for node in nodes]
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=_MenuDumper, sort_keys=False, allow_unicode=True)


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


def _join_and(values) -> str:
    values = list(values)
    return f"{', '.join(values[:-1])} and {values[-1]}"
