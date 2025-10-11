#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MENU_ROOT="${SCRIPT_DIR}/scripts"

if ! command -v zenity >/dev/null 2>&1; then
  echo "Error: zenity is required but was not found in PATH." >&2
  exit 1
fi

if [[ ! -d "${MENU_ROOT}" ]]; then
  echo "Error: MENU_ROOT directory '${MENU_ROOT}' does not exist." >&2
  exit 1
fi

# Use the proper way to set starting directory for zenity file selection
# The filename parameter should point to a file in the desired directory
dummy_file="${MENU_ROOT}/dummy"
selection=$(zenity --file-selection \
  --title="Commander" \
  --filename="${dummy_file}" \
  --file-filter="Shell scripts | *.sh" \
  --file-filter="All files | *" \
  2>/dev/null) || exit 0

if [[ -z "${selection}" ]]; then
  exit 0
fi

if [[ "${selection}" != "${MENU_ROOT}"/* ]]; then
  zenity --error --text="Selected file must be inside ${MENU_ROOT}."
  exit 1
fi

if [[ ! -f "${selection}" ]]; then
  zenity --error --text="Selected item is not a file."
  exit 1
fi

run_with_bash=false
if [[ ! -x "${selection}" ]]; then
  zenity --question --text="${selection} isn't marked executable. Run it with bash?" --default-cancel --ok-label="Run" --cancel-label="Cancel" || exit 0
  run_with_bash=true
fi

resolve_realpath() {
  local path="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$path"
    return
  fi

  if command -v readlink >/dev/null 2>&1; then
    local resolved
    if resolved=$(readlink -f "$path" 2>/dev/null); then
      echo "$resolved"
      return
    fi
    # Manual resolution fallback using readlink without -f support
    local target="$path"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      return 1
    fi

    while [[ -L "$target" ]]; do
      local dir
      dir=$(cd -P "$(dirname "$target")" && pwd) || return 1
      local link
      link=$(readlink "$target") || return 1
      if [[ "$link" == /* ]]; then
        target="$link"
      else
        target="$dir/$link"
      fi
    done

    local final_dir
    final_dir=$(cd -P "$(dirname "$target")" && pwd) || return 1
    echo "$final_dir/$(basename "$target")"
    return
  fi

  return 1
}

if ! resolved_selection=$(resolve_realpath "${selection}"); then
  zenity --error --text="Unable to resolve the selected script's real path."
  exit 1
fi

if [[ -z "${resolved_selection}" || ! -f "${resolved_selection}" ]]; then
  zenity --error --text="Unable to resolve the selected script's real path."
  exit 1
fi

resolved_dir=$(dirname "${resolved_selection}")

launch_in_terminal() {
  local command_to_run="$1"
  export COMMAND_TO_RUN="${command_to_run}"
  local shell_snippet='eval "$COMMAND_TO_RUN"; exit_code=$?; echo; read -rp "Press Enter to close..."; exit $exit_code'

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal -- bash -lc "${shell_snippet}"
  elif command -v konsole >/dev/null 2>&1; then
    konsole -e bash -lc "${shell_snippet}"
  elif command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal --hold --command="bash -lc '${shell_snippet}'"
  elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e bash -lc "${shell_snippet}"
  elif command -v xterm >/dev/null 2>&1; then
    xterm -e bash -lc "${shell_snippet}"
  else
    zenity --error --text="No supported terminal emulator found."
    exit 1
  fi
}

if [[ "${run_with_bash}" == true ]]; then
  cmd=$(printf 'cd %q && bash %q' "${resolved_dir}" "${resolved_selection}")
else
  cmd=$(printf 'cd %q && %q' "${resolved_dir}" "${resolved_selection}")
fi

launch_in_terminal "${cmd}"
