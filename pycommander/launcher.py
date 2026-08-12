"""Running the picked script.

Three modes, carried over unchanged from the original Commander's trailing
underscore conventions:

  detached  no terminal window at all, output discarded          (was: no suffix)
  terminal  fresh window; closes the moment the script exits     (was: "_")
  hold      fresh window; held open until the user hits Enter    (was: "__")

Everything is spawned with start_new_session=True and its streams pointed at
/dev/null. That is what lets the menu window stay open after a launch: the
child belongs to its own session, so quitting PyCommander never takes it down,
and no pipe can ever fill up and stall the GUI thread.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess

from .menu import LAUNCH_DETACHED, LAUNCH_HOLD, MenuNode

# Same preference order the original commander.sh used.
TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "x-terminal-emulator", "xterm")


def launch(node: MenuNode) -> str | None:
    """Run `node`'s script. Returns an error message, or None on success."""
    if node.is_section:
        return f"'{node.name}' is a section, not a script."
    if node.file is not None and not os.path.isfile(node.resolved_file):
        return f"Cannot launch '{node.name}':\n\n{node.resolved_file}\n\nNo such file."

    cwd = node.resolved_cwd
    if not os.path.isdir(cwd):
        return f"Cannot launch '{node.name}':\n\nWorking directory does not exist:\n{cwd}"

    cmd = build_command(node)

    if node.launch == LAUNCH_DETACHED:
        argv = ["bash", "-lc", cmd]
    else:
        argv = _terminal_argv(cmd, title=node.name)
        if argv is None:
            return (
                f"Cannot launch '{node.name}' in a terminal:\n\n"
                f"No supported terminal emulator found. Tried: {', '.join(TERMINALS)}."
            )

    try:
        _spawn(argv)
    except OSError as exc:
        return f"Cannot launch '{node.name}':\n\n{exc}"
    return None


def build_command(node: MenuNode) -> str:
    """The `bash -c` program that runs `node` under its launch mode.

    An inline `sh` snippet needs no file on disk: bash -c takes a whole
    multi-line program just as happily as a one-liner, and the shell running
    it *is* the terminal's only process, so the launch modes behave exactly as
    they do for a real script file.
    """
    hold = node.launch == LAUNCH_HOLD
    cd = f"cd {shlex.quote(node.resolved_cwd)} || exit 1"

    if node.sh is not None:
        label = node.name
        body = node.sh.rstrip("\n")
        if hold:
            # Parenthesised so a bare `exit` in the snippet ends the snippet
            # rather than the whole shell, which would skip the epilogue below
            # and drop the window. A real script file gets this for free by
            # running as its own process. The "(" rides on the cd's line so
            # bash's reported line numbers stay a constant +1 off the snippet.
            lines = [f"{cd}; (", body, ")"]
        else:
            lines = [cd, body]
    else:
        path = node.resolved_file
        label = os.path.basename(path)
        # A script without the execute bit still runs, just under an explicit bash.
        runner = shlex.quote(path)
        if not os.access(path, os.X_OK):
            runner = f"bash {runner}"
        # `exec` hands the terminal straight to the script, so the window's
        # lifetime is the script's — except under `hold`, below.
        lines = [cd, runner if hold else f"exec {runner}"]

    if hold:
        # Deliberately nothing exec'd above: the script would become the
        # terminal's only process, so one that finishes quickly (or fails)
        # would take the window down with it before its output could be read.
        # Keeping a shell behind it holds the window open until dismissed.
        # Joined by newlines rather than ';' so a snippet whose last line is a
        # comment doesn't swallow the epilogue.
        lines += [
            "rc=$?",
            "printf '\\n[pycommander] %s exited with status %s — press Enter to close…' "
            f"{shlex.quote(label)} \"$rc\"",
            "read -r",
        ]

    return "\n".join(lines)


def _terminal_argv(cmd: str, title: str) -> list[str] | None:
    """Wrap `cmd` in the first terminal emulator we can find."""
    for term in TERMINALS:
        if not shutil.which(term):
            continue
        if term == "gnome-terminal":
            return [term, "--title", title, "--", "bash", "-lc", cmd]
        if term == "xfce4-terminal":
            # xfce4-terminal takes its command as a single string, so re-quote.
            return [term, "--title", title, "--command", f"bash -lc {shlex.quote(cmd)}"]
        if term == "xterm":
            return [term, "-T", title, "-e", "bash", "-lc", cmd]
        return [term, "-e", "bash", "-lc", cmd]  # konsole, x-terminal-emulator
    return None


def _spawn(argv: list[str]) -> None:
    # bash -lc (a *login* shell) so scripts see the same PATH and profile they
    # would get from a real terminal, not the stripped-down desktop session env.
    subprocess.Popen(
        argv,
        env=_child_env(),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _child_env() -> dict[str, str]:
    """Our environment minus PyCommander's own virtualenv.

    start.sh runs us through `uv run`, which puts .venv/bin on PATH and sets
    VIRTUAL_ENV. Left in place those leak into every launched script, so a
    script that runs `python` would get PyCommander's interpreter instead of
    the system one. Launched scripts should see the environment they'd get
    from a terminal, not ours.
    """
    env = os.environ.copy()
    venv = env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if venv:
        bin_dir = os.path.normpath(os.path.join(venv, "bin"))
        path = env.get("PATH", "")
        kept = [p for p in path.split(os.pathsep) if p and os.path.normpath(p) != bin_dir]
        env["PATH"] = os.pathsep.join(kept)
    return env
