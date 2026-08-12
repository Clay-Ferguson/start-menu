# PyCommander User Guide

## What PyCommander Is

PyCommander is a small, keyboard-driven menu application for launching your own
scripts and commands. Instead of hunting through folders or remembering
command lines, you define a menu of items — organized into folders if you
like — and PyCommander shows it to you as a simple, navigable list. Pick an
item, press Enter, and it runs.

The whole menu lives in a single window that shows **one level at a time**.
Opening a folder replaces the list with that folder's contents rather than
expanding a tree in place, so the window stays the same size no matter how
deep your menu gets. The mouse is never required — every feature, including
editing the menu, can be driven entirely from the keyboard.

Everything you see in the menu is backed by a menu file on disk. You can edit
that menu — adding, renaming, reordering, and removing folders and items —
directly from within the app, or by opening the underlying file in a text
editor. Both ways are covered below.

## Starting PyCommander

PyCommander is started with the path to a menu file:

```bash
./start.sh /path/to/menu.yaml
```

If the file you point it at doesn't exist yet, PyCommander creates it
automatically with a small starter item, so pointing it at a brand-new path
just works — you'll have something to look at and edit immediately.

If the menu file exists but has a problem (invalid YAML, or a menu entry
that's missing something it needs), PyCommander won't open a broken window —
instead it shows a dialog listing every problem found, so you can fix them
all in one pass before trying again.

## The Main Window

The window has four parts, top to bottom:

- **Header** — shows your current location as a breadcrumb (e.g.
  `Applications / Browsers`) whenever you've navigated into a folder. At the
  top level, where there's nothing to show, it disappears entirely.
- **Edit toolbar** — two buttons, **New Folder** and **New Item**. Hidden
  unless edit mode is turned on (see [Edit Mode](#edit-mode)).
- **The menu list** — the current folder's items, one per row, each with an
  icon and a label.
- **Footer** — the edit mode toggle switch, and a row of key hints
  (`⏎ launch    e edit menu    q quit`).

Hovering over an item shows a tooltip with more detail about it: the resolved
path for a file-based item, the first several lines of an inline script, or
the number of items inside a folder.

## Navigating the Menu

Navigation uses four keys, and nothing else is needed to use the menu:

| Key | Action |
|---|---|
| `↑` / `↓` | Move the highlight up or down within the current level |
| `→` | Open the highlighted folder (does nothing if the highlight is on a launchable item) |
| `←` | Back up one level; the highlight lands on the folder you just came out of |
| `⏎` (Enter) | Launch the highlighted item, or open the highlighted folder |

Double-clicking a row with the mouse does the same thing Enter does.

At the very top level, pressing `←` does nothing — there's nowhere further
back to go.

### Launching an Item

Pressing Enter (or double-clicking) on a launchable item runs it immediately.
The PyCommander window **stays open** afterward, so you can fire off several
things in a row without reopening the app. Whatever you launch runs
independently of PyCommander — closing the menu window doesn't stop anything
you've started.

If something goes wrong while launching (a missing script file, a missing
working directory, or no terminal emulator available), a dialog explains what
happened. A script file living on a drive that isn't currently mounted, for
example, isn't detected until you actually try to launch it.

Every launchable item runs in one of three ways, decided when the item was
created or edited:

| Mode | What you see | Typical use |
|---|---|---|
| **Detached (no window)** | Nothing — it runs silently in the background | GUI applications: browsers, editors, file managers |
| **Terminal (closes when it exits)** | A new terminal window that closes the instant the command finishes | Interactive commands, or anything that prompts you |
| **Hold (stays open until you press Enter)** | A new terminal window that stays open after the command finishes, showing its exit status, until you press Enter | Commands that print a report and then exit quickly, so you have time to read the output |

### Quitting

Press `Esc` or `q` at any time to close the window.

## Edit Mode

By default, PyCommander opens ready to *use* the menu, not change it. To
modify anything — add, rename, reorder, or remove folders and items — turn on
**Edit mode** using the switch in the bottom-left corner of the window (next
to the "Edit" label).

Turning edit mode on does two things:

1. The **New Folder** and **New Item** buttons appear in the toolbar just
   below the header.
2. The currently highlighted row grows a set of small action icons on its
   right edge: **move up**, **move down**, **edit**, and **delete** (in that
   order, right to left). These icons only ever appear on the highlighted
   row — move the highlight with the arrow keys and they follow it.

Edit mode is **not remembered** between runs — every time you start
PyCommander, it opens with edit mode off, so you don't accidentally leave the
menu editable.

Every change you make — creating, editing, deleting, or reordering an item —
is saved to the menu file immediately and automatically. There's no separate
"Save" step and no undo; each action asks for confirmation first when it's
destructive (see [Deleting an Item](#deleting-an-item)), and takes effect as
soon as you confirm it. After saving, PyCommander reloads the file from disk
and returns you to the same folder you were in, with the same item
highlighted where possible.

### The Row Action Icons

While edit mode is on, the highlighted row shows up to four icons:

- **↑ Move up** — swaps the item with the one above it. Not shown on the
  first item in a level, since there's nowhere for it to go.
- **↓ Move down** — swaps the item with the one below it. Not shown on the
  last item in a level.
- **✎ Edit** — opens the editor for that row (the [folder name
  dialog](#renaming-a-folder) for a folder, or the [item editor
  dialog](#the-item-editor-dialog) for a launchable item).
- **🗑 Delete** — removes the item, after confirming.

Click an icon with the mouse to trigger it, or use `↑`/`↓` to move the
highlight to the row you want and click its icons — the action icons don't
have their own keyboard shortcuts, since which ones apply changes row to row.

### Creating a New Folder

With edit mode on, click **New Folder**. A small dialog asks for the folder's
name; type it and click **Save** (or **Cancel** to back out). The **Save**
button stays disabled until you've typed something, since a folder can't be
left unnamed.

The new folder is added to the **end** of whichever level you're currently
viewing — the top level, or whatever folder you've navigated into. It starts
out empty; step into it with `→` and use **New Item** to start populating it.
Unlike the top-level menu (which always needs at least one item), a folder is
allowed to stay empty.

### Renaming a Folder

Click a folder's ✎ **edit** icon (with edit mode on and that folder
highlighted). The same simple name dialog described above appears, pre-filled
with the current name — change it and click **Save**.

### Creating a New Item

With edit mode on, click **New Item**. This opens the [item editor
dialog](#the-item-editor-dialog), described in full below, with all fields
blank. Fill it in and click **Save** to add it.

Like a new folder, the new item is appended to the end of whichever level is
currently shown on screen.

### Editing an Existing Item

Click a launchable item's ✎ **edit** icon. The same [item editor
dialog](#the-item-editor-dialog) opens, pre-filled with that item's current
name, file/script, and launch mode. Change what you like and click **Save**.

### The Item Editor Dialog

This dialog is used both to create a new launchable item and to edit an
existing one — the fields work identically either way.

- **Name** — the label shown in the menu. Required; **Save** stays disabled
  while this is blank.
- **File / Bash script** — a pair of radio buttons choosing what kind of
  item this is:
  - **File** shows a text field for a path to a script on disk, plus a
    **Pick File…** button that opens a standard file-browser dialog so you
    don't have to type the path by hand.
  - **Bash script** shows a multi-line text editor where you can type (or
    paste) shell commands directly — no separate script file needed. Longer
    scripts scroll normally; the box is sized to show a reasonably long
    script without scrolling at all.

  Switching between the two radio buttons swaps which editor is shown; only
  one of the two is ever saved (whichever is currently selected).
- **Launch** — a dropdown choosing how the item runs, with the same three
  modes described in [Launching an Item](#launching-an-item): *Detached (no
  window)*, *Terminal (closes when it exits)*, and *Hold (stays open until
  you press Enter)*.

**Save** stays disabled until the Name field and the selected content field
(File path or Bash script text) both have something in them — an item can't
be saved half-finished. **Cancel** discards whatever you've typed and closes
the dialog without changing anything.

### Deleting an Item

Click a row's 🗑 **delete** icon. A confirmation dialog asks you to confirm,
naming the item; if it's a folder with items inside it, the dialog also warns
you how many items will be deleted along with it, since deleting a folder
deletes everything inside it too.

The one restriction: the top-level menu can never be left completely empty.
If you try to delete the last remaining item at the very top level,
PyCommander refuses and explains why. A folder, unlike the top level, is
allowed to end up empty.

### Reordering Items

Use a row's ↑ and ↓ action icons to move it earlier or later within its
current level. Items can only be reordered within the level they're in —
there's no drag-and-drop, and moving an item into a different folder isn't
supported directly (edit the item to point somewhere else, or edit the menu
file by hand for that kind of restructuring).

## Opening the Menu File Directly

Press `e` at any time (edit mode doesn't need to be on) to open the menu file
itself in a text editor — useful for changes the GUI doesn't offer directly,
like reordering into a different folder, or bulk edits across many items.

Which editor opens is controlled by the menu file's `options.editor` setting
(see below); if that isn't set, PyCommander falls back to the `$VISUAL` or
`$EDITOR` environment variables, and finally to your desktop's default
handler for `.yaml` files.

The PyCommander window stays open while you edit, but it does **not**
automatically notice your changes — edits made this way take effect the next
time PyCommander is started, not immediately. (Edits made through the GUI's
own dialogs, by contrast, take effect right away, since PyCommander made them
itself and reloads the file after saving.)

## Icons

Every row shows an icon: a folder icon by default for folders, a generic file
icon by default for launchable items. You can give an item or folder its own
icon by setting `icon:` in the menu file — either the name of an icon from
your desktop's icon theme (e.g. `utilities-terminal`) or a path to an image
file. There's no GUI control for this yet; it's set by editing the menu file
directly (see below).

## The Menu File

Everything above is driven by a single YAML file — the one you pointed
`start.sh` at. You don't need to hand-edit this file to use PyCommander; the
Edit-mode tools cover creating, renaming, reordering, and deleting folders
and items. This section is a reference for anyone who wants to edit the file
directly (via `e`), or understand what the GUI is actually writing.

### Structure

The file has two top-level keys:

```yaml
options:
  editor: code

menu:
  - folder: Applications
    icon: applications-other
    items:
      - name: Firefox
        icon: firefox
        file: /usr/bin/firefox
        launch: detached

  - name: Disk report
    launch: hold
    sh: |
      echo "Free space:"
      df -h /
```

`menu:` holds the list of top-level items; items appear in the order written
— there's no automatic sorting. Every entry in `menu:` (or inside a folder's
`items:`) is exactly one of three things, decided by which key it carries:

| Key | Makes it a… | Notes |
|---|---|---|
| `items` | **folder** (labeled by `folder:`) | holds a nested list of items, in the same format |
| `file` | **script on disk** (labeled by `name:`) | path to a script; `~` and `$VARS` are expanded and symlinks resolved |
| `sh` | **inline snippet** (labeled by `name:`) | shell commands written directly in the YAML, using a `|` block for anything longer than one line |

### Other keys

| Key | Applies to | Meaning |
|---|---|---|
| `launch` | script | `detached`, `terminal`, or `hold` (see [Launching an Item](#launching-an-item)); defaults to `terminal` |
| `cwd` | script | Working directory to run in. Defaults to the script's own directory for `file:`, or `$HOME` for `sh:` |
| `icon` | folder or script | An icon theme name, or a path to an image file |
| `options.editor` | top-level setting | The shell command `e` uses to open this file; may include arguments (e.g. `code -n`) |

### Validation

The file is fully validated every time PyCommander starts. If anything is
wrong, PyCommander reports **every** problem it finds in one pass (not just
the first one), each tagged with the offending entry's location, e.g.:

```
menu.yaml has 2 problem(s):

  • menu[2].items[1] (status): unknown launch mode 'bogus'; expected one of detached, hold, terminal.
  • menu[4] (Lingo Web): has both 'items:' and 'file:' — an item is either a section (items) or a script (file), not both.
```

Any reported problem prevents the window from opening at all, since the menu
tree can't be trusted to be complete — fix the file and start PyCommander
again. A missing script file is *not* caught at this stage (it might live on
a drive that isn't mounted yet); that's only reported if you try to launch
it.
