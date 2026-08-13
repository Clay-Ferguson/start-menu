"""Running the picked script.

Four modes. The first three are carried over unchanged from the original
Commander's trailing underscore conventions:

  detached  no terminal window at all, output discarded          (was: no suffix)
  terminal  fresh window; closes the moment the script exits     (was: "_")
  hold      fresh window; held open until the user hits Enter    (was: "__")
  tmux      window attaches to a named tmux session that outlives it

Everything is spawned with start_new_session=True and its streams pointed at
/dev/null. That is what lets the menu window stay open after a launch: the
child belongs to its own session, so quitting PyCommander never takes it down,
and no pipe can ever fill up and stall the GUI thread.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess

from .menu import LAUNCH_DETACHED, LAUNCH_HOLD, LAUNCH_TMUX, MenuNode

# Same preference order the original commander.sh used.
TERMINALS = ("gnome-terminal", "konsole", "xfce4-terminal", "x-terminal-emulator", "xterm")

# Stricter than tmux itself requires. tmux addresses panes as
# `session:window.pane`, so a ':' or '.' inside the *session* name makes every
# `-t` below aim at some other window or pane instead of the session.
TMUX_SESSION_RE = re.compile(r"[A-Za-z0-9_-]+")

# Shown in the tmux status bar, since the way out of an attached session is
# the one thing about this mode that isn't guessable.
TMUX_DETACH_HINT = " Ctrl+B D = detach (process keeps running) "


def launch(node: MenuNode) -> str | None:
    """Run `node`'s script. Returns an error message, or None on success."""
    if node.is_section:
        return f"'{node.name}' is a section, not a script."

    # Checked before `file:`, since a relative `file:` (e.g. a bare filename
    # from "Pick File…" — see dialogs.py) only resolves against a valid `cwd:`.
    cwd = node.resolved_cwd
    if not cwd:
        return (
            f"Cannot launch '{node.name}':\n\n"
            "No working directory is set for this item.\n\n"
            "Edit the item and choose one."
        )
    if not os.path.isdir(cwd):
        return f"Cannot launch '{node.name}':\n\nWorking directory does not exist:\n{cwd}"

    if node.file is not None and not os.path.isfile(node.resolved_file):
        return f"Cannot launch '{node.name}':\n\n{node.resolved_file}\n\nNo such file."

    if node.launch == LAUNCH_TMUX:
        session = (node.tmux_session or "").strip()
        if not session:
            return (
                f"Cannot launch '{node.name}':\n\n"
                "No tmux session name is set for this item.\n\n"
                "Edit the item and choose one."
            )
        if not TMUX_SESSION_RE.fullmatch(session):
            return (
                f"Cannot launch '{node.name}':\n\n"
                f"'{session}' is not a usable tmux session name.\n\n"
                "Use only letters, digits, '_' and '-'. In particular ':' and '.'\n"
                "are how tmux separates a session from a window or pane, so a name\n"
                "containing either would address the wrong thing."
            )
        # Checked here as well as in the generated script: a PATH lookup is
        # free and gives an instant dialog, instead of a terminal window
        # flashing open only to fail inside it.
        if shutil.which("tmux") is None:
            return (
                f"Cannot launch '{node.name}':\n\n"
                "tmux is not installed.\n\nInstall it with:  sudo apt install tmux"
            )

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

    `tmux` mode builds the same program every other mode would, then hands it
    to `_build_tmux_wrapper` to be run inside a tmux session rather than
    directly in the window.
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

    if node.launch == LAUNCH_TMUX:
        # No hold-style epilogue for tmux: remain-on-exit is tmux's own version
        # of that, and it keeps the output readable in the pane whether or not
        # anything is attached at the time.
        return _build_tmux_wrapper(node, "\n".join(lines), label)

    return "\n".join(lines)


def _build_tmux_wrapper(node: MenuNode, inner: str, label: str) -> str:
    """Wrap `inner` in the script that runs it inside a named tmux session.

    A port of llama-deck's hand-written tmuxer.sh, generalized from "run this
    script path" to "run this generated command". The shape is: clear the
    session if its process has already died, create it (detached) if it isn't
    there, then attach. Attaching is the only part the terminal window itself
    does, which is why closing that window merely detaches — the process
    belongs to the tmux server, not to the window.

    Built by plain concatenation rather than f-strings on purpose: tmux's own
    format syntax ('#{pane_dead}' below) is full of braces an f-string would
    try to evaluate.
    """
    name = node.tmux_session.strip()
    session = shlex.quote(name)
    # Two levels of quoting: the inner one makes the generated program a single
    # argument to `bash -lc`, the outer one makes the whole `bash -lc ...`
    # string a single argument to `tmux new-session`. `-lc` (a login shell)
    # keeps PATH/profile behavior identical to every other launch mode.
    shell_cmd = shlex.quote("bash -lc " + shlex.quote(inner))
    hint = shlex.quote(TMUX_DETACH_HINT)

    # printf '%s' does not expand escapes, so these need real newlines in the
    # text itself rather than '\n' sequences.
    no_tmux_msg = shlex.quote(
        "tmux is not installed.  Install it with:  sudo apt install tmux\n"
        "Press Enter to close…"
    )
    unattachable_msg = shlex.quote(
        "The tmux session exists, but this window could not attach to it.\n"
        "See it from any terminal with:  tmux attach -t " + name + "\n"
        "Press Enter to close…"
    )
    died_msg = shlex.quote(
        "The process exited immediately, before its output could be captured.\n"
        "Run " + label + " directly to see why.\n"
        "Press Enter to close…"
    )

    lines = [
        # The window has no shell behind it on these paths, so anything printed
        # would vanish with the window; hold it open the way `hold` mode does.
        "hold() { printf '\\n%s' \"$1\"; read -r; }",
        # Belt-and-braces: launch() already checked this in Python, which is
        # what gives the fast dialog. This only catches tmux disappearing
        # between the click and this script running.
        "if ! command -v tmux >/dev/null 2>&1; then hold " + no_tmux_msg + "; exit 1; fi",
        # A session whose process already exited is debris: attaching would show
        # a dead pane and never start anything. remain-on-exit (set below) is
        # what leaves it detectable here instead of the session silently
        # vanishing along with the error output.
        "if tmux has-session -t " + session + " 2>/dev/null; then",
        '  if [ "$(tmux list-panes -t %s -F \'#{pane_dead}\' 2>/dev/null'
        ' | sort -u)" = "1" ]; then' % session,
        "    tmux kill-session -t " + session + " 2>/dev/null",
        "  fi",
        "fi",
        "if ! tmux has-session -t " + session + " 2>/dev/null; then",
        # remain-on-exit must be set in this same tmux invocation, not a
        # following one: the likeliest real failure (a port already in use, say)
        # exits in milliseconds, and a second tmux process cannot win that race
        # — the session would already be gone, taking the error message with it.
        # Chained with \; so tmux, not the outer bash, reads the semicolons.
        "  tmux new-session -d -s " + session + " " + shell_cmd
        + " \\; set-option -t " + session + " remain-on-exit on"
        + " \\; set-option -t " + session + " status-right " + hint,
        "fi",
        "if ! tmux attach-session -t " + session + " 2>/dev/null; then",
        # Two very different failures, and naming the wrong one sends you
        # hunting a problem that isn't there.
        "  if tmux has-session -t " + session + " 2>/dev/null; then",
        "    hold " + unattachable_msg,
        "  else",
        "    hold " + died_msg,
        "  fi",
        "  exit 1",
        "fi",
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
