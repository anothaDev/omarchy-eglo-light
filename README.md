# Eglo Light — an Omarchy bar plugin for Eglo Connect / AwoX lamps

Control **Eglo Connect** and other **AwoX Bluetooth-mesh** lamps straight from
the [Omarchy](https://omarchy.org) bar. No app, no cloud account, no hub: your
computer's own Bluetooth talks to the lamp.

- Bar icon shows on/off and tints with the lamp's current colour.
  Left click opens the panel, right click toggles power, scroll changes brightness.
- Panel: power switch, brightness, white warmth, twelve colour swatches and
  the lamp's built-in colour-cycle "party" mode.
- Keyboard like the stock panels: `j`/`k` move, `h`/`l` adjust, `Enter` apply,
  `t` toggle, `c` change lamp, `Esc` close.
- Commands land in about 100 ms. The remote keeps working alongside.

## Requirements

- Omarchy 4 (the Quickshell shell) with a working Bluetooth adapter.
- `python3` with the `venv` module (stock on Omarchy). The first run creates a
  private virtualenv under `~/.local/share/eglo-light/` with
  [bleak](https://github.com/hbldh/bleak) and pycryptodome; that needs network
  access once. Those wheels and their dependencies are pinned to exact
  versions and verified against the SHA-256 hashes in `requirements.txt`, so
  the install can only ever fetch the artefacts the maintainer reviewed
  (maintainers: the file header documents how to regenerate the pins). Linux
  x86_64 and aarch64 on CPython 3.13/3.14 are covered; if you upgrade Python,
  the venv is rebuilt automatically the next time you open the panel.
- A lamp of the *Bluetooth* Eglo Connect generation (or another AwoX
  SmartLIGHT). Eglo **connect.z** lamps are Zigbee and are not supported.

## Install

```bash
omarchy plugin add https://github.com/anothaDev/omarchy-eglo-light.git --enable
```

Then open the panel from the bar. It scans for lamps in range and lists them;
pick yours and you are done. One widget controls one lamp; support for more
than one lamp is planned.

Which lamps work out of the box:

| Lamp advertises as | Situation | Credentials |
|---|---|---|
| `R-XXXXXX` | paired with the Eglo/AwoX remote | filled in automatically |
| `unpaired` | factory fresh (glows red) | filled in automatically |
| anything else | set up in the Eglo/AwoX app | mesh name and password from your app account, see below |

If your lamp is factory fresh, you can simply hold the remote's **ON** button
for three seconds near it, then scan again.

### Supported devices

Every lamp broadcasts its product id, and the panel adapts to what the lamp
can do: colour lamps get the full panel, tunable-white lamps get brightness,
warmth and white presets, dimmable lamps get brightness only, plugs get a
switch. The product table in `awoxlight/devices.py` covers about 110 Eglo,
AwoX and Keria products (bulbs, spots, panels, ceiling lights, strips,
plugs) and comes from the
[EspHome-AwoX-BLE-mesh-hub](https://github.com/fsaris/EspHome-AwoX-BLE-mesh-hub)
project. An unknown product id gets the full panel so nothing is hidden by
mistake. Tested end to end on an Eglo Giron-C (32589); reports for other
models are welcome.

For an app-managed lamp, set the mesh credentials on the widget:

```bash
omarchy bar set anothadev.eglo-light meshName  "<mesh name>"
omarchy bar set anothadev.eglo-light meshPassword "<mesh password>"
```

Tools such as [awoxble2mqtt-api](https://github.com/BastiAKA/awoxble2mqtt-api)
or [home-assistant-awox](https://github.com/fsaris/home-assistant-awox) can
export them from an AwoX account.

## Settings

Stored on the widget in `~/.config/omarchy/shell.json`, editable with
`omarchy bar set anothadev.eglo-light <key> <value>`:

| Key | Meaning |
|---|---|
| `name` | Label shown in the panel |
| `mac` | Lamp Bluetooth address (set from the panel) |
| `meshName`, `meshPassword` | Mesh credentials (set from the panel) |
| `pollIntervalSec` | Background state poll, default 20 |

## Keybindings and scripting

The panel registers the IPC target `anothadev.eglo-light`:

```lua
-- ~/.config/hypr/bindings.lua
o.bind("SUPER + SHIFT + L", "Toggle lamp", "omarchy-shell anothadev.eglo-light toggleLight")
o.bind("SUPER + ALT + L",   "Lamp panel",  "omarchy-shell anothadev.eglo-light toggle")
```

Methods: `toggleLight`, `on`, `off`, `brightness <0-100>`, `color <#rrggbb>`,
`refresh`, `status`, and `open`/`close`/`toggle` for the panel. With several
widget instances the IPC target belongs to the first one.

There is also a CLI, handy for scripts and cron:

```bash
lightctl=~/.config/omarchy/plugins/anothadev.eglo-light/bin/lightctl
$lightctl scan                                     # lamps in range and their mesh

export LIGHT_MAC=A4:C1:38:.. MESH_NAME=R-XXXXXX MESH_PASSWORD=1234
$lightctl toggle
$lightctl color '#ff8000' 60                       # colour + brightness %
$lightctl white 80 70                              # brightness %, warmth %
$lightctl preset 0                                 # built-in colour sequence
```

`cron` and `at` jobs must also set `XDG_RUNTIME_DIR=/run/user/$UID`: the plugin
keeps its socket, lock and log there and refuses to run without it.

The `LIGHT_MAC`, `MESH_NAME` and `MESH_PASSWORD` environment variables save the
repetition and, unlike the equivalent `--mac` / `--mesh-name` /
`--mesh-password` options, keep the mesh password out of the command line,
where every other local user could read it with `ps`.

## How it works

Eglo Connect lamps use the Telink BLE mesh protocol. Any BLE central can
connect to the lamp's GATT server at any time; what the mesh calls pairing is
an application-level login, an AES challenge/response keyed on the mesh name
XOR mesh password. The lamp advertises its mesh name as its Bluetooth name,
and remote-paired and factory-fresh meshes use the fixed password `1234`.

The lamp also broadcasts its live state (power, mode, brightness, warmth,
RGB) in its BLE advertisements, so state is read passively.

```
Panel.qml ──lightctl──▶ awoxlight.daemon ──BLE──▶ lamp(s)
 (bar UI)   (unix socket)  scans beacons,
                           holds one link per lamp
```

A BLE connect costs 2–4 s while a command on an open link takes ~100 ms, so
the daemon holds the link. A lamp freezes its beacon while a central is
connected, so every 90 s of idle time the daemon drops the link for a few
seconds to pick up a fresh beacon. That is how changes made with the remote
or a wall switch are noticed, with up to that much delay.

The daemon starts on demand, serves any number of lamps, and exits after ten
minutes without requests. Log: `$XDG_RUNTIME_DIR/eglo-light.log`.

`awoxlight/` is a bleak (BlueZ) port of the protocol documented in
[python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light).
Protocol tests: `python -m pytest tests`.

## Troubleshooting

- **"Not in range or switched off"**: the lamp has not been heard for a
  while. Bluetooth range is the main limit; the lamp must be powered at the
  wall.
- **"Mesh credentials rejected"**: the lamp was re-paired (its advertised
  `R-` name changed). Press `c` in the panel and pick it again.
- **"Bluetooth is off"**: `omarchy toggle bluetooth`, or check `bluetoothctl show`.
- **Installing never finishes**: see `~/.local/share/eglo-light/install.log`.
  An install that was interrupted (logout, OOM, power loss) recovers by
  itself: the lock is an `flock` the kernel releases when the installer dies,
  so the next launch simply starts a new install. An install that *failed* is
  reported for 10 minutes — so the panel can show the error — and is then
  retried automatically on the next launch. Deleting
  `~/.local/share/eglo-light` and opening the panel again is still the manual
  reset.

## License

MIT.
