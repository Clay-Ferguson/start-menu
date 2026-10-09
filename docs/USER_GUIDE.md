# Start Menu User Guide

## What Start Menu Is

Start Menu is a small, keyboard-driven menu application for launching your own scripts and commands. Instead of hunting through folders or remembering command lines, you define a menu of items — organized into folders if you like — and Start Menu shows it to you as a simple, navigable list. Pick an item, press Enter, and it runs.

The whole menu lives in a single window that shows **one level at a time**. Opening a folder replaces the list with that folder's contents rather than expanding a tree in place, so the window stays the same size no matter how deep your menu gets. The mouse is never required — every feature, including editing the menu, can be driven entirely from the keyboard.

Everything you see in the menu is backed by a menu file on disk. You can edit that menu — adding, renaming, reordering, and removing folders and items — directly from within the app, or by opening the underlying file in a text editor. Both ways are covered below.

![](/docs/img/app-window.png)

## Running Start Menu

If you installed Start Menu as a package, it's in your application launcher, and `start-menu` runs it from a terminal. From a source checkout it's `./start.sh`. Either way you can name a menu file, or let it use the default:

```bash
start-menu                        # installed: uses ~/.config/start-menu/menu.yaml
./start.sh                        # from a checkout: the same default
./start.sh /path/to/menu.yaml     # or exactly the file you name
```

If the file doesn't exist yet — including that default one, the first time you ever run Start Menu — it's created for you as a copy of the bundled example menu, so you land in a working menu with something to look at and edit immediately rather than a blank window.

If the menu file exists but has a problem (invalid YAML, or a menu entry that's missing something it needs), Start Menu won't open a broken window — instead it shows a dialog listing every problem found, so you can fix them all in one pass before trying again.

## The Main Window

The window has four parts, top to bottom:

- **Menu bar** — an **Edit** menu holding **New Folder** (`Ctrl+Shift+N`) and **New Item** (`Ctrl+N`), then **Cut** (`Ctrl+X`), **Undo Cut** (`Ctrl+Z`) and **Paste** (`Ctrl+V`). The menu bar is only shown in edit mode, and even then each item is greyed out unless it applies right now (see [Moving Items Between Folders](#moving-items-between-folders)).
- **Header** — a back arrow (`←`) button plus your current location as a breadcrumb (e.g. `Applications / Browsers`), shown whenever you've navigated into a folder. Clicking the arrow backs up one level, the same as pressing `←`. At the top level, where there's nothing to show and nowhere to back up to, the whole header disappears.
- **The menu list** — the current folder's items, one per row, each with an icon and a label.
- **Footer** — the edit mode toggle switch, and a row of key hints (`⏎ launch    e edit menu    q quit`).

Hovering over an item shows a tooltip with more detail about it: the resolved path for a file-based item, the first several lines of an inline script, or the number of items inside a folder.

## Navigating the Menu

Navigation uses four keys, and nothing else is needed to use the menu:

| Key | Action |
|---|---|
| `↑` / `↓` | Move the highlight up or down within the current level |
| `→` | Open the highlighted folder (does nothing if the highlight is on a launchable item) |
| `←` | Back up one level; the highlight lands on the folder you just came out of |
| `⏎` (Enter) | Launch the highlighted item, or open the highlighted folder |

Double-clicking a row with the mouse does the same thing Enter does, and the back arrow in the header does the same thing `←` does — so the menu is fully usable with the mouse alone.

At the very top level, pressing `←` does nothing — there's nowhere further back to go (and the header, with its back arrow, isn't shown there at all).

### Launching an Item

Pressing Enter (or double-clicking) on a launchable item runs it immediately. The Start Menu window **stays open** afterward, so you can fire off several things in a row without reopening the app. Whatever you launch runs independently of Start Menu — closing the menu window doesn't stop anything you've started.

If something goes wrong while launching (a missing script file, a missing working directory, or no terminal emulator available), a dialog explains what happened. A script file living on a drive that isn't currently mounted, for example, isn't detected until you actually try to launch it.

Every launchable item runs in one of four ways, decided when the item was created or edited:

| Mode | What you see | Typical use |
|---|---|---|
| **Detached (no terminal)** | Nothing — it runs silently in the background | GUI applications: browsers, editors, file managers |
| **Terminal (terminal auto-closes)** | A new terminal window that closes the instant the command finishes | Interactive commands, or anything that prompts you |
| **Hold (terminal stays open)** | A new terminal window that stays open after the command finishes, showing its exit status, until you press Enter | Commands that print a report and then exit quickly, so you have time to read the output |
| **Tmux (session keeps running)** | A new terminal window showing the command running inside a named tmux session; closing the window leaves it running | Long-running things — a server, a watcher, a long build — you want to leave running and check back on later (see [Tmux Sessions](#tmux-sessions)) |

### Quitting

Press `Esc` at any time to close the window.

## Edit Mode

By default, Start Menu opens ready to *use* the menu, not change it. To modify anything — add, rename, reorder, or remove folders and items — turn on **Edit mode** using the switch in the bottom-left corner of the window (next to the "Edit" label).

![](/docs/img/settings-dialog.png)

Turning edit mode on does three things:

1. The menu bar appears, with its **Edit** menu: **New Folder** and **New Item** are always available, **Cut**, **Undo Cut** and **Paste** whenever they apply (see [Moving Items Between Folders](#moving-items-between-folders)), and **Update Nautilus** and **Clear Nautilus** (see [Nautilus Integration](#nautilus-integration)).
2. The currently highlighted row grows a set of action icons on its right edge: **move up**, **move down**, **edit**, and **delete** (in that order, right to left). These icons only ever appear on the highlighted row — move the highlight with the arrow keys and they follow it.
3. You can select more than one row at a time — hold **Ctrl** and click to add or remove individual rows, or hold **Shift** and click to select a run of them. This is only useful for **Cut**; turning edit mode back off collapses the selection to a single row again.

Edit mode is **not remembered** between runs — every time you start Start Menu, it opens with edit mode off, so you don't accidentally leave the menu editable.

Every change you make — creating, editing, deleting, or reordering an item — is saved to the menu file immediately and automatically. There's no separate "Save" step and no undo; each action asks for confirmation first when it's destructive (see [Deleting an Item](#deleting-an-item)), and takes effect as soon as you confirm it. After saving, Start Menu reloads the file from disk and returns you to the same folder you were in, with the same item highlighted where possible.

### The Row Action Icons

While edit mode is on, the highlighted row shows up to four icons:

- **↑ Move up** — swaps the item with the one above it. Not shown on the first item in a level, since there's nowhere for it to go.
- **↓ Move down** — swaps the item with the one below it. Not shown on the last item in a level.
- **✎ Edit** — opens the editor for that row (the [folder name dialog](#renaming-a-folder) for a folder, or the [item editor dialog](#the-item-editor-dialog) for a launchable item).
- **🗑 Delete** — removes the item, after confirming.

Click an icon with the mouse to trigger it, or use `↑`/`↓` to move the highlight to the row you want and click its icons — the action icons don't have their own keyboard shortcuts, since which ones apply changes row to row.

### Creating a New Folder

With edit mode on, choose **Edit → New Folder** (`Ctrl+Shift+N`). A small dialog asks for the folder's name; type it and click **Save** (or **Cancel** to back out). The **Save** button stays disabled until you've typed something, since a folder can't be left unnamed.

The new folder is added to the **end** of whichever level you're currently viewing — the top level, or whatever folder you've navigated into. It starts out empty; step into it with `→` and use **New Item** to start populating it. Unlike the top-level menu (which always needs at least one item), a folder is allowed to stay empty.

### Renaming a Folder

Click a folder's ✎ **edit** icon (with edit mode on and that folder highlighted). The same simple name dialog described above appears, pre-filled with the current name — change it and click **Save**.

### Creating a New Item

With edit mode on, choose **Edit → New Item** (`Ctrl+N`). This opens the [item editor dialog](#the-item-editor-dialog), described in full below, with all fields blank. Fill it in and click **Save** to add it.

Like a new folder, the new item is appended to the end of whichever level is currently shown on screen.

### Editing an Existing Item

Click a launchable item's ✎ **edit** icon. The same [item editor dialog](#the-item-editor-dialog) opens, pre-filled with that item's current name, file/script, working directory, and launch mode. Change what you like and click **Save**.

### The Item Editor Dialog

This dialog is used both to create a new launchable item and to edit an existing one — the fields work identically either way.

- **Name** — the label shown in the menu. Required; **Save** stays disabled while this is blank.
- **File / Bash script** — a pair of radio buttons choosing what kind of item this is:
  - **File** shows a text field for a path to a script on disk, plus a **Pick File…** button that opens a standard file-browser dialog so you don't have to type the path by hand.
  - **Bash script** shows a multi-line text editor where you can type (or paste) shell commands directly — no separate script file needed. Longer scripts scroll normally; the box is sized to show a reasonably long script without scrolling at all.

  Switching between the two radio buttons swaps which editor is shown; only one of the two is ever saved (whichever is currently selected).
- **Working directory** — a text field for the folder the item runs from, plus a **Pick Folder…** button that opens a standard folder-browser dialog so you don't have to type the path by hand. This applies whether the item is a **File** or a **Bash script**, and is required — see [Working Directory](#working-directory-cwd) below.
- **Launch** — a dropdown choosing how the item runs, with the same four modes described in [Launching an Item](#launching-an-item): *Detached (no window)*, *Terminal (terminal auto-closes)*, *Hold (terminal stays open)*, and *Tmux (session keeps running)*.
- **Tmux session name** — a text field that appears **only** when the launch mode is set to *Tmux*, naming the session the item attaches to. It accepts letters, digits, `_` and `-` only; other characters simply won't type. See [Tmux Sessions](#tmux-sessions).
- **Show in Nautilus on** — a dropdown that appears **only** for items in the `Nautilus` folder: *Folders* or *Files*, the kind of thing the item is offered on when right-clicked in Nautilus. See [Nautilus Integration](#nautilus-integration).

**Save** stays disabled until the Name field, the selected content field (File path or Bash script text), and the Working directory field all have something in them — plus the Tmux session name, if the Tmux launch mode is selected. An item can't be saved half-finished. **Cancel** discards whatever you've typed and closes the dialog without changing anything.

Switching the launch mode away from *Tmux* hides the session-name field but doesn't forget what you typed in it — switch back and it's still there.

### Working Directory

Every launchable item needs a working directory — the folder it runs from. There's no automatic default (e.g. a script's own folder); it's a required field you fill in yourself, in the [item editor dialog](#the-item-editor-dialog) or as `cwd:` in the YAML.

If an item's working directory is left empty or points at a folder that no longer exists, launching it doesn't fail silently — a dialog explains the problem at the moment you try to launch it, the same as a missing script file does (see [Launching an Item](#launching-an-item)). A menu file written before `cwd:` existed will hit this on every item until you edit each one to add it.

### Tmux Sessions

Normally, closing a terminal window kills whatever was running in it. That's fine for a script that finishes on its own, but not for something you want to leave running — a development server, a long build, a download. The **Tmux** launch mode solves that by running the item inside a named [tmux](https://github.com/tmux/tmux) session, which keeps running whether or not any window is showing it.

What that looks like in practice:

- **Launch the item.** A terminal window opens with your command running in it, and a reminder in the status bar at the bottom: `Ctrl+B D = detach`.
- **Close the window** — either by pressing `Ctrl+B` then `D`, or just closing it with the mouse. Both are safe: the command keeps running in the background.
- **Launch the same item again later.** Start Menu notices the session is still running and asks what you want:
  - **Attach** — reconnect to the one already running, with all its earlier output still scrolled back behind it. This is the default.
  - **Restart** — stop that session and run the item again from scratch.
  - **Cancel** — do nothing; no window opens.

  The question includes **when the session was started**, which is worth reading. Attaching does not re-run anything, so if you've edited the script since that time, the running session is still the *old* version — restarting is what picks up your changes. (Restart ends everything in that session, so anything you've since started inside it goes too.)
- **If the command has finished or crashed** in the meantime, launching starts it fresh without asking. Its last output is kept on screen rather than disappearing with the window, so a command that fails immediately still leaves you something to read.

Each Tmux item needs a **session name** — this is what Start Menu uses to find the running session again next time. Give each item its own name unless you deliberately want two items to share one session; two items with the same name will connect to the same running command. The name has to match exactly, so an item named `web` will never pick up a session called `web-staging`.

Session names allow letters, digits, `_` and `-` only. (tmux itself treats `:` and `.` as separators inside a session name, so allowing them would make Start Menu connect to the wrong thing.) The item editor's field simply won't accept other characters.

This mode requires the `tmux` program to be installed. On Ubuntu or Debian: `sudo apt install tmux`. Like a missing script file or working directory, a missing `tmux`, a missing session name, or one containing illegal characters (possible only if the menu file was hand-edited) isn't reported when Start Menu starts — you get a dialog explaining it at the moment you try to launch the item.

A session started this way is also reachable from any ordinary terminal with `tmux attach -t <session name>`, and `tmux ls` lists everything currently running.

### Deleting an Item

Click a row's 🗑 **delete** icon. A confirmation dialog asks you to confirm, naming the item; if it's a folder with items inside it, the dialog also warns you how many items will be deleted along with it, since deleting a folder deletes everything inside it too.

The one restriction: the top-level menu can never be left completely empty. If you try to delete the last remaining item at the very top level, Start Menu refuses and explains why. A folder, unlike the top level, is allowed to end up empty.

### Reordering Items

Use a row's ↑ and ↓ action icons to move it earlier or later within its current level. There's no drag-and-drop; to move something into a *different* folder, cut and paste it (below).

### Moving Items Between Folders

Cut and paste moves launchable items from one folder to another. It works on several items at once, and only in edit mode.

1. Select what you want to move: click one row, or Ctrl-click / Shift-click to select several. **Edit → Cut** becomes available as soon as at least one launchable item is selected.
2. Choose **Edit → Cut** (or press `Ctrl+X`). The selected rows disappear from the list — that's how you can tell what's waiting to be moved. Nothing has actually changed yet: the menu file on disk is untouched, and the items are simply hidden until they land somewhere.
3. Navigate to wherever you want them (`→` into folders, `←` back out, as usual), then choose **Edit → Paste** (`Ctrl+V`). The items are added to the **end** of whichever level you're looking at, and the menu file is written out immediately.

While items are waiting to be pasted, **Cut** is greyed out and **Undo Cut** (`Ctrl+Z`) and **Paste** are available instead. **Undo Cut** simply brings the hidden rows back where they were — since a cut never moved anything, there's nothing else to undo.

A few things worth knowing:

- **Folders can't be cut.** Only launchable items can be moved this way. If your selection includes a folder, Start Menu says so and does nothing — deselect the folder and click **Cut** again. (To restructure folders themselves, [edit the menu file directly](#opening-the-menu-file-directly).)
- **Cut replaces the previous cut.** Whatever is selected when you click **Cut** becomes the whole set of items waiting to be pasted; you can't walk around the menu cutting a few items here and a few there and expect them to pile up.
- **Any other edit cancels a pending cut.** Creating, renaming, deleting, or reordering something while items are waiting to be pasted brings those items back into view instead. Nothing is lost — they never left the menu. Turning edit mode off does the same.
- Pasting into the same folder you cut from is allowed; it just moves those items to the end of that folder.

## Nautilus Integration

Start Menu can add items to the right-click menu of **Nautilus** (the Files app), run on whatever file or folder you right-clicked. It replaces the separate *Coral* extension.

### Setting It Up

1. Create a folder at the **top level** of the menu named exactly **`Nautilus`** (Edit → New Folder).
2. Put the items you want in Nautilus directly inside it, with Edit → New Item as usual. Folders inside it are ignored.
3. For each item, choose **Show in Nautilus on**: *Folders* (the default) or *Files*.
4. Choose **Edit → Update Nautilus**. The first time, Start Menu offers to restart Nautilus, which it needs in order to load the menu. Restarting closes any open Nautilus windows. Say no and the menu appears the next time Nautilus starts.

Run **Update Nautilus** again whenever you add, rename or remove items in the folder. After the first time, an update takes effect immediately, with no restart. Changes to what an item *does* (its script, working directory, launch mode) need no update at all, since each launch reads the menu file fresh.

To take all of Start Menu's items off Nautilus's menu, choose **Edit → Clear Nautilus**. It takes effect immediately, with no restart, and leaves your `Nautilus` folder untouched; **Update Nautilus** puts the items back.

Nautilus needs its Python extension support for this: `sudo apt install python3-nautilus`. Update Nautilus tells you if it's missing.

### What an Item Is Given

When an item runs from Nautilus, it gets the right-clicked path in environment variables:

| Right-clicked | `$TARGET_FOLDER` | `$TARGET_FILE` |
|---|---|---|
| a folder | that folder | *(not set)* |
| a file | the folder the file is in | that file |

Use them in a Bash script (`code "$TARGET_FOLDER"`), or in a script file, which inherits them. They are also filled in when they appear in the item's own **Working directory** or **File** field. Those fields accept them with or without shell-style quotes, so `$TARGET_FOLDER` and `"$TARGET_FOLDER"` both work. `$TARGET_FOLDER` as the working directory runs the item in the right-clicked folder (or the clicked file's folder), and `$TARGET_FILE` as the File runs the right-clicked file itself.

Every launch mode works from Nautilus just as it does from the Start Menu window, including *Hold* and *Tmux*. If something goes wrong, for example the item was renamed and Nautilus's menu not yet updated, Start Menu shows a dialog.

Nautilus only shows these items when a **single** file or folder is right-clicked, and adds nothing to the menu you get by right-clicking empty space. Its menus have no icons, so an item's `icon:` isn't shown there; an emoji at the start of the name works instead. One name can be used at most once for *Folders* and once for *Files*.

You can also launch a Nautilus item from the Start Menu window itself, which is handy for trying one out. Since nothing was right-clicked, Start Menu first asks you to choose the target: a file picker titled *Menu Item requires File* for a *Files* item, or a folder picker titled *Menu Item requires Folder* for a *Folders* item. The item then runs exactly as if you had right-clicked your choice in Nautilus. Cancel the picker and nothing runs. Each picker opens where your previous choice was.

### Examples

```yaml
  - folder: Nautilus
    items:
      - name: Open in VS Code
        launch: detached
        cwd: $TARGET_FOLDER
        sh: code "$TARGET_FOLDER"

      - name: Open Terminal Here
        launch: detached
        cwd: $TARGET_FOLDER
        sh: gnome-terminal --working-directory="$TARGET_FOLDER"

      - name: Run Script
        target_type: file
        launch: hold
        cwd: $TARGET_FOLDER
        file: $TARGET_FILE

      - name: Copy Full Path          # needs: sudo apt install xclip
        target_type: file
        launch: detached
        cwd: $TARGET_FOLDER
        sh: printf %s "$TARGET_FILE" | xclip -selection clipboard

      - name: Copy Full Path          # the same, for folders
        launch: detached
        cwd: $TARGET_FOLDER
        sh: printf %s "$TARGET_FOLDER" | xclip -selection clipboard
```

## Opening the Menu File Directly

You can also open the menu file itself (normally `~/.config/start-menu/menu.yaml`) in any text editor — useful for changes the GUI doesn't offer directly, like moving a whole folder somewhere else, or bulk edits across many items.

A running Start Menu does **not** automatically notice your changes — edits made this way take effect the next time Start Menu is started, not immediately. (Edits made through the GUI's own dialogs, by contrast, take effect right away, since Start Menu made them itself and reloads the file after saving.)

If you edit the file this way and then, in the same session, make a change through the GUI, Start Menu notices the file has changed underneath it. Rather than overwrite your edit, it leaves the file alone, says so, and reloads the menu from the file — make the GUI change again and it will save normally.

Note that saving from the GUI rewrites the whole file, so any comments you have written in it are dropped the first time you make a change through Edit mode.

## Icons

Every row shows an icon: a folder icon by default for folders, a generic file icon by default for launchable items. You can give an item or folder its own icon by setting `icon:` in the menu file — either the name of an icon from your desktop's icon theme (e.g. `utilities-terminal`) or a path to an image file. There's no GUI control for this yet; it's set by editing the menu file directly (see below).

## The Menu File

Everything above is driven by a single YAML file — the one you pointed `start.sh` at. You don't need to hand-edit this file to use Start Menu; the Edit-mode tools cover creating, renaming, reordering, moving, and deleting folders and items. This section is a reference for anyone who wants to edit the file directly in a text editor, or understand what the GUI is actually writing.

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
        cwd: ~

  - name: Disk report
    launch: hold
    cwd: ~
    sh: |
      echo "Free space:"
      df -h /
```

`menu:` holds the list of top-level items; items appear in the order written — there's no automatic sorting. Every entry in `menu:` (or inside a folder's `items:`) is exactly one of three things, decided by which key it carries:

| Key | Makes it a… | Notes |
|---|---|---|
| `items` | **folder** (labeled by `folder:`) | holds a nested list of items, in the same format |
| `file` | **script on disk** (labeled by `name:`) | path to a script; `~` and `$VARS` are expanded and symlinks resolved |
| `sh` | **inline snippet** (labeled by `name:`) | shell commands written directly in the YAML, using a `|` block for anything longer than one line |

### Other keys

| Key | Applies to | Meaning |
|---|---|---|
| `launch` | script | `detached`, `terminal`, `hold`, or `tmux` (see [Launching an Item](#launching-an-item)); defaults to `terminal` |
| `cwd` | script | Working directory to run in. Required — see [Working Directory](#working-directory-cwd) |
| `tmux_session` | script | Name of the tmux session to use. Required when `launch: tmux`, ignored otherwise — see [Tmux Sessions](#tmux-sessions) |
| `target_type` | script | `folder` (the default) or `file`: what the item is offered on in Nautilus. Only used inside the `Nautilus` folder — see [Nautilus Integration](#nautilus-integration) |
| `icon` | folder or script | An icon theme name, or a path to an image file |
| `options.editor` | top-level setting | The shell command the item editor's **Edit** button opens a script file with; may include arguments (e.g. `code -n`). Falls back to `$VISUAL`, `$EDITOR`, then your desktop's default handler |

### Validation

The file is fully validated every time Start Menu starts. If anything is wrong, Start Menu reports **every** problem it finds in one pass (not just the first one), each tagged with the offending entry's location, e.g.:

```
menu.yaml has 2 problem(s):

  • menu[2].items[1] (status): unknown launch mode 'bogus'; expected one of detached, hold, terminal, tmux.
  • menu[4] (Lingo Web): has both 'items:' and 'file:' — an item is either a section (items) or a script (file), not both.
```

Any reported problem prevents the window from opening at all, since the menu tree can't be trusted to be complete — fix the file and restart Start Menu. A missing script file, a missing or empty `cwd:`, or a missing or malformed `tmux_session:`, is *not* caught at this stage (a script might live on a drive that isn't mounted yet, and an item edited before `cwd:` existed simply has none); those are only reported if you try to launch the item — see [Working Directory](#working-directory-cwd) and [Tmux Sessions](#tmux-sessions).
