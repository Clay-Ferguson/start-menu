"""Running the picked script.

Four modes. The first three are carried over unchanged from the original
Commander's trailing underscore conventions:

  detached  no terminal window at all, output discarded          (was: no suffix)
  terminal  fresh window; closes the moment the script exits     (was: "_")
  hold      fresh window; held open until the user hits Enter    (was: "__")
  tmux      window attaches to a named tmux session that outlives it

Everything is spawned with start_new_session=True and its streams pointed at
/dev/null. That is what lets the menu window stay open after a launch: the
child belongs to its own session, so quitting Start Menu never takes it down,
and no pipe can ever fill up and stall the GUI thread.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from typing import Callable

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

# What `tmux_session_state` found. "dead" means the session is still there but
# every pane in it has exited — debris left behind by remain-on-exit, which the
# generated wrapper clears on its own, so it needs no decision from the user.
TMUX_ABSENT = "absent"
TMUX_LIVE = "live"
TMUX_DEAD = "dead"

# What the caller's `on_running_session` hook may answer. ATTACH is what this
# mode has always done on its own.
TMUX_ATTACH = "attach"
TMUX_RESTART = "restart"
TMUX_CANCEL = "cancel"


def launch(
    node: MenuNode,
    on_running_session: Callable[[MenuNode, str, str | None], str] | None = None,
) -> str | None:
    """Run `node`'s script. Returns an error message, or None on success.

    `on_running_session` is consulted only in tmux mode, and only when the
    item's session already exists with something still alive in it — the case
    where "launch" would otherwise silently mean "reattach to what was started
    the last time", never re-reading the script. It is called with
    `(node, session_name, started)` — `started` being a human-readable local
    time, or None if tmux wouldn't say — and answers TMUX_ATTACH (the historic
    behavior), TMUX_RESTART (kill the session first, so the script runs again
    from disk) or TMUX_CANCEL (do nothing at all). Left unset, this behaves
    exactly as it did before: attach.

    A cancelled launch returns None, same as a successful one: nothing ran,
    but nothing went wrong either, and the caller has nothing to report.
    """
    if node.is_section:
        return f"'{node.name}' is a section, not a script."

    # Checked before `file:`, since a relative `file:` (e.g. a bare filename
    # from "Pick File…" — see dialogs/) only resolves against a valid `cwd:`.
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
        # Asked here rather than inside the generated script for the same
        # reason as the checks above: from here it can be a dialog, and the
        # answer decides whether a window is worth opening at all.
        if on_running_session is not None and tmux_session_state(session) == TMUX_LIVE:
            choice = on_running_session(node, session, tmux_session_started(session))
            if choice == TMUX_CANCEL:
                return None
            if choice == TMUX_RESTART:
                error = kill_tmux_session(session)
                if error:
                    return f"Cannot restart '{node.name}':\n\n{error}"

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
            "printf '\\n[start-menu] %s exited with status %s — press Enter to close…' "
            f"{shlex.quote(label)} \"$rc\"",
            "read -r",
        ]

    if node.launch == LAUNCH_TMUX:
        # No hold-style epilogue for tmux: remain-on-exit is tmux's own version
        # of that, and it keeps the output readable in the pane whether or not
        # anything is attached at the time.
        return _build_tmux_wrapper(node, "\n".join(lines))

    return "\n".join(lines)


def _build_tmux_wrapper(node: MenuNode, inner: str) -> str:
    """Wrap `inner` in the script that runs it inside a named tmux session.

    Three steps: clear the session if its process has already died, create it
    (detached) if it isn't there, then attach. Attaching is the only part the
    terminal window itself does, which is why closing that window merely
    detaches — the process belongs to the tmux server, not to the window.

    The checks that actually fire in practice (no tmux, no session name) are
    done in Python by `launch`, so they can be dialogs. What's left here is
    the handful of failures that can only be discovered mid-flight, and each
    one holds the window open to say so rather than letting it blink shut.

    Built by plain concatenation rather than f-strings on purpose: tmux's own
    format syntax ('#{pane_dead}' below) is full of braces an f-string would
    try to evaluate.
    """
    name = node.tmux_session.strip()
    session = shlex.quote(name)  # for `-s`, which names a session rather than finds one
    target = _tmux_target(name)
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
    # "Run it directly to see why" only means something when there's a file to
    # run; an inline snippet has no such thing.
    retry_hint = (
        "Run " + node.resolved_file + " directly to see why."
        if node.file is not None
        else "Check this item's commands for something that exits straight away."
    )
    died_msg = shlex.quote(
        "The process exited immediately, before its output could be captured.\n"
        + retry_hint + "\n"
        "Press Enter to close…"
    )

    lines = [
        # The window has no shell behind it on these paths, so anything printed
        # would vanish with the window; hold it open the way `hold` mode does.
        "hold() { printf '\\n%s' \"$1\"; read -r; }",
        # Start Menu may itself have been started from a terminal inside tmux,
        # in which case $TMUX has been inherited all the way down to here — and
        # tmux refuses to attach when it thinks it's nesting. This window is a
        # brand new one, not a pane, so the inherited value is simply stale.
        "unset TMUX TMUX_PANE",
        # launch() already checked this in Python, which is what makes the
        # normal case a dialog. Repeating it here isn't just belt-and-braces:
        # without it a vanished tmux would fail every command below and be
        # reported as "the process exited immediately", which is the wrong
        # thing to go hunting for.
        "if ! command -v tmux >/dev/null 2>&1; then hold " + no_tmux_msg + "; exit 1; fi",
        # A session whose process already exited is debris: attaching would show
        # a dead pane and never start anything. remain-on-exit (set below) is
        # what leaves it detectable here instead of the session silently
        # vanishing along with the error output.
        #
        # `-s` covers every window in the session, not just its current one,
        # and `sort -u` collapses the result, so this reads as "every pane in
        # there is dead" — if the user has split off something that's still
        # alive, we reattach to it instead of killing their session.
        "if tmux has-session -t " + target + " 2>/dev/null; then",
        '  if [ "$(tmux list-panes -s -t %s -F \'#{pane_dead}\' 2>/dev/null'
        ' | sort -u)" = "1" ]; then' % target,
        "    tmux kill-session -t " + target + " 2>/dev/null",
        "  fi",
        "fi",
        "if ! tmux has-session -t " + target + " 2>/dev/null; then",
        # remain-on-exit must be set in this same tmux invocation, not a
        # following one: the likeliest real failure (a port already in use, say)
        # exits in milliseconds, and a second tmux process cannot win that race
        # — the session would already be gone, taking the error message with it.
        # Chained with \; so tmux, not the outer bash, reads the semicolons.
        #
        # -w because remain-on-exit is a window option (it lands on the window
        # just created); status-right is a session option, so it takes none.
        #
        # Plain `session`, not the exact `target` used everywhere else:
        # set-option is one of the commands that does *not* accept the '='
        # prefix (it reports "no such window", and the chain fails, leaving
        # remain-on-exit unset). It needs no exactness anyway — new-session
        # has just created this name, so tmux's own exact match finds it first.
        "  tmux new-session -d -s " + session + " " + shell_cmd
        + " \\; set-option -w -t " + session + " remain-on-exit on"
        + " \\; set-option -t " + session + " status-right " + hint,
        "fi",
        "if ! tmux attach-session -t " + target + " 2>/dev/null; then",
        # Two very different failures, and naming the wrong one sends you
        # hunting a problem that isn't there.
        "  if tmux has-session -t " + target + " 2>/dev/null; then",
        "    hold " + unattachable_msg,
        "  else",
        "    hold " + died_msg,
        "  fi",
        "  exit 1",
        "fi",
    ]
    return "\n".join(lines)


def tmux_session_state(name: str) -> str:
    """Whether session `name` is absent, live, or dead debris.

    Deliberately the same test the generated wrapper makes on itself (see
    `_build_tmux_wrapper`): every pane in the session, across all its windows,
    reporting `pane_dead` is what makes it debris. If the user has split off
    something that's still running, the session counts as live and restarting
    it would take that down too — which is exactly why the choice is theirs.

    Any trouble running tmux at all reads as TMUX_ABSENT: this only decides
    whether to *ask* a question, and the wrapper still does the real work, so
    guessing "absent" costs at most an unasked question rather than an error
    about something the user can't act on.
    """
    if shutil.which("tmux") is None:
        return TMUX_ABSENT
    target = "=" + name
    if _tmux("has-session", "-t", target) is None:
        return TMUX_ABSENT
    panes = _tmux("list-panes", "-s", "-t", target, "-F", "#{pane_dead}")
    if not panes:
        return TMUX_ABSENT
    return TMUX_DEAD if set(panes.split()) == {"1"} else TMUX_LIVE


def tmux_session_started(name: str) -> str | None:
    """When session `name` was created, as local time — or None if unknown.

    Worth the extra call purely because of what it answers: a session started
    days ago is running whatever the script said *then*, and the timestamp is
    the quickest way to see that's what you're looking at.

    Listed and matched here rather than asked for by target: `display-message`
    reads its `-t` as a target *pane*, where the '=' exact-match prefix used
    everywhere else silently resolves to nothing. Comparing names from
    `list-sessions` is exact by construction, with no target syntax involved.
    """
    listing = _tmux("list-sessions", "-F", "#{session_created} #{session_name}")
    if not listing:
        return None
    for line in listing.splitlines():
        # Split once only: a session name may itself contain spaces.
        created, _, session = line.partition(" ")
        if session != name:
            continue
        try:
            return time.strftime("%a %d %b %Y, %H:%M", time.localtime(int(created)))
        except (ValueError, OSError):
            return None
    return None


def kill_tmux_session(name: str) -> str | None:
    """End session `name` and everything in it. Error message, or None."""
    if _tmux("kill-session", "-t", "=" + name) is None:
        return f"tmux could not end the session '{name}'."
    # kill-session returns as soon as the server has dropped the session, so a
    # launch that follows this reliably finds it gone and starts a fresh one.
    return None


def _tmux_target(name: str) -> str:
    """Session `name` as a `-t` target, quoted for the generated shell script.

    The '=' prefix is what makes tmux match the name *exactly*. Without it a
    `-t` target falls back to prefix and pattern matching, so an item whose
    session is 'llama' would find, attach to — and on a restart, kill — an
    unrelated 'llama-deck' session that happened to be running. A session name
    typed into the menu file is meant literally, never as a pattern.
    """
    return shlex.quote("=" + name)


def _tmux(*args: str) -> str | None:
    """Run a tmux command, returning its stdout — or None if it failed.

    Short-lived queries against the local tmux server, so unlike the launched
    scripts these are run and waited on. `_child_env` for the same reason the
    scripts get it: Start Menu's own virtualenv has no business here.
    """
    try:
        result = subprocess.run(
            ["tmux", *args],
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


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
    """Our environment minus Start Menu's own virtualenv.

    start.sh runs us through `uv run`, which puts .venv/bin on PATH and sets
    VIRTUAL_ENV. Left in place those leak into every launched script, so a
    script that runs `python` would get Start Menu's interpreter instead of
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
