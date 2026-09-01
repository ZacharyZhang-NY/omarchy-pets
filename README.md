# Omarchy Pets

A desktop pet for the [Omarchy](https://omarchy.org) bar. It plays
[Codex Pets](https://codex-pets.net) sprite sheets straight from
`~/.codex/pets/`, moves on its own every 8–20 seconds, turns its head toward
your pointer, waves when clicked, and can be pinned to the desktop and dragged
anywhere on the screen.

![Dragging the pinned pet around the desktop, then switching pets from the panel](preview.gif)

## Requirements

- Omarchy 4 (Quattro) with its Quickshell bar, `omarchy-shell`, on Hyprland.
- `python3`, which every Omarchy install already has (the base packages
  `uwsm`, `ufw` and `udiskie` depend on it). It checks each pet's `pet.json`
  and sprite sheet when the panel opens.
- At least one pet from <https://codex-pets.net>, unzipped into
  `~/.codex/pets/<id>/` (the same place Codex itself reads). Pets are not
  part of this repository.

## Install

```sh
omarchy plugin add https://github.com/ZacharyZhang-NY/omarchy-pets.git --enable
```

The bar shows the current pet's first frame; with no pets it shows a paw.

## Use

- Click the pet in the bar to open the panel: the animated pet, the first
  three installed pets, and the settings. Escape or a click outside closes it.
- Click a pet in the list to switch. The choice survives shell restarts. With
  more than three pets, "View all" opens the full list; "Back" returns.
- Hover the pet and it looks at the pointer (v2 sheets only); click it and it
  waves.
- The pin button (top-right of the pet) keeps the pet on the desktop with the
  panel closed. It never takes keyboard focus and only the pet itself is
  clickable. Drag the pinned pet to put it anywhere on the screen; the spot is
  remembered. Click the bar icon to unpin.

## Settings

All of them live in the widget's entry in `~/.config/omarchy/shell.json` and
can be set from the CLI:

```sh
omarchy bar set raiden-meixelysia.omarchy-pets smooth false --json
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `petId` | string | `""` | Directory name of the current pet; empty means the first one |
| `petsDir` | string | `~/.codex/pets` | Where pets are read from |
| `smooth` | bool | `true` | Bilinear scaling; turn off for pixel-art pets |
| `pinned` | bool | `false` | Keep the pet on the desktop |
| `pinnedX` | int | `-1` | Left edge of the pinned pet in screen pixels; `-1` is below the bar icon. Dragging sets it |
| `pinnedY` | int | `-1` | Top edge of the pinned pet; same rules |
| `randomBehavior` | bool | `true` | Play a random move every 8–20 s |
| `animate` | bool | `true` | Off shows one still frame and runs no timer |

## What it touches

- Reads `~/.codex/pets/` (or the `petsDir` override) each time the panel
  opens. It never creates, renames or deletes anything there.
- Runs `scan.py` under `timeout` once per scan. It opens each `pet.json` and
  sprite sheet without following symlinks, insists on regular files (64 KiB
  and 32 MiB caps), reads only the WebP or PNG header for the size (1536
  wide, 9 to 32 rows of 208, PNG at most 8 bits per channel), looks at no more than 500 entries and is
  killed after 10 seconds. No image is decoded outside the shell's own
  bounded `Image`. No network access, no installer, nothing run as root.
- Writes only its own settings (the keys above) into the bar layout in
  `~/.config/omarchy/shell.json`, through the shell's plugin registry, which
  is the same path `omarchy bar set` uses.

## Remove

```sh
omarchy plugin remove raiden-meixelysia.omarchy-pets
```

This deletes the plugin folder after taking a backup. The widget's settings
line in `~/.config/omarchy/shell.json` stays behind; delete it if you want a
clean file. `~/.codex/pets/` is untouched.

## Develop

```sh
omarchy plugin validate .
/usr/lib/qt6/bin/qmllint -I "$OMARCHY_PATH/shell" *.qml
/usr/lib/qt6/bin/qmltestrunner -input test
python3 -m unittest discover -s test -p 'test_scan.py'
```

The plugin runs inside `omarchy-shell`; after changing files under
`~/.config/omarchy/plugins/`, restart the shell (`omarchy restart shell`) and
check `journalctl --user | grep omarchy-pets`.

## Credits

Sprite format from [Codex Pets](https://codex-pets.net); frame timing from
[Petdex](https://github.com/crafter-station/petdex) (MIT). Pet assets are
third-party uploads with unclear licences and are not part of this repository.

## License

MIT — see [LICENSE](LICENSE).
