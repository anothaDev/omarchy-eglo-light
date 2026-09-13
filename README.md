# Eglo Light

An [Omarchy](https://omarchy.org) bar plugin for **Eglo Connect**, **AwoX
SmartLIGHT** and **Keria** Bluetooth-mesh lamps. No app, no cloud account, no
hub: your computer's own Bluetooth talks to the lamp. Unofficial; not
affiliated with Eglo or AwoX.

- Bar icon shows on/off and tints with the lamp's current colour. Left click
  opens the panel, right click toggles power, scroll changes brightness.
- Panel: power switch, brightness, white warmth, twelve colour swatches and
  the lamp's built-in colour-cycle mode. The panel adapts to what the lamp can
  do (colour, tunable white, dimmable, plug).
- Keyboard like the stock panels: `j`/`k` move, `h`/`l` adjust, `Enter` apply,
  `t` toggle, `c` change lamp, `Esc` close.
- Commands land in about 100 ms. The lamp's own remote keeps working alongside.

## Supported lamps

The plugin speaks the Telink Bluetooth-mesh protocol used by the AwoX
SmartLIGHT platform, which Eglo and Keria sell under their own brands. It
recognises 114 products by the product id every lamp broadcasts and shows only
the controls that lamp has.

| Brand | What is covered | Examples |
|---|---|---|
| **Eglo Connect** (Bluetooth generation) | bulbs, spots, panels, ceiling and pendant lights, LED strips, outdoor lights, filament bulbs, plugs | EGLOBulb A60/G95, EGLOSpot, EGLOPanel, Giron, Fueva, Fraioli, Frattina, EGLO Plug Plus |
| **AwoX SmartLIGHT** | Color Mesh and White Mesh bulbs (E27, E14, GU10) | SmartLIGHT Color Mesh 9W/13W/15W, White Mesh 9W/13W/15W |
| **Keria** | SmartLIGHT Color Mesh bulbs | Keria SmartLIGHT Color Mesh 9W/13W/5W |

Capabilities by kind: colour lamps get the full panel; tunable-white lamps get
brightness, warmth and white presets; dimmable lamps get brightness only;
plugs get a switch. An unknown product id gets the full panel so nothing is
hidden by mistake. The table lives in `awoxlight/devices.py` and comes from
the [EspHome-AwoX-BLE-mesh-hub](https://github.com/fsaris/EspHome-AwoX-BLE-mesh-hub)
project. Tested end to end on an Eglo Giron-C (32589); reports for other
models are welcome.

**Not supported:** Eglo **connect.z** (Zigbee), Eglo **connect-c** (2.4 GHz
remote only), Eglo **access**, and Eglo or AwoX Wi-Fi products. They use
different radios.

### How a lamp gets its credentials

A lamp advertises its mesh name as its Bluetooth name; the plugin's scan reads
it and fills in the credentials for you where it can:

| Lamp advertises as | Situation | Credentials |
|---|---|---|
| `R-XXXXXX` | paired with the Eglo/AwoX remote | filled in automatically |
| `unpaired` | factory fresh (glows red) | filled in automatically |
| anything else | set up in the Eglo/AwoX app | mesh name and password from your app account, see [Settings](#settings) |

A factory-fresh lamp can also be adopted by holding the remote's **ON** button
for three seconds near it, then scanning again.

## Requirements

- Omarchy 4 (the Quickshell shell) with a working Bluetooth adapter (BlueZ).
- `python3` with the `venv` module, `bash`, `flock` (util-linux) and GNU
  coreutils. All are part of a standard Omarchy installation.
- Network access once, at first run, to fetch two Python libraries.

No sudo or pkexec is required, and the plugin never asks for either.

### External dependencies

The first run creates a private virtualenv under `~/.local/share/eglo-light/`
and installs exactly these packages, pinned by version and SHA-256 hash in
`requirements.txt` (`pip install --require-hashes --only-binary`):

| Package | Version | Purpose | License |
|---|---|---|---|
| [bleak](https://github.com/hbldh/bleak) | 3.0.2 | Bluetooth LE via BlueZ | MIT |
| [dbus-fast](https://github.com/Bluetooth-Devices/dbus-fast) | 5.0.22 | D-Bus transport used by bleak | MIT |
| [pycryptodome](https://github.com/Legrandin/pycryptodome) | 3.23.0 | AES for the mesh handshake | BSD / public domain |

Linux x86_64 and aarch64 on CPython 3.13 and 3.14 are covered. After a Python
upgrade the virtualenv is rebuilt automatically the next time the panel is
opened. Maintainers: the header of `requirements.txt` documents how to
regenerate the pins.

## Install

### With the plugin manager

```bash
omarchy plugin add https://github.com/anothaDev/omarchy-eglo-light.git --enable
```

The widget appears on the right side of the bar. Open it, wait for the scan,
pick your lamp, done. If you prefer to review the code first, omit `--enable`,
inspect `~/.config/omarchy/plugins/anothadev.eglo-light/`, then run
`omarchy plugin enable anothadev.eglo-light`.

### Manual install (without the plugin manager)

```bash
mkdir -p "$HOME/.config/omarchy/plugins"
git clone -- https://github.com/anothaDev/omarchy-eglo-light.git \
  "$HOME/.config/omarchy/plugins/anothadev.eglo-light"
omarchy-shell shell rescanPlugins
omarchy bar put anothadev.eglo-light --section right --after omarchy.tray
```

The folder name must equal the plugin id. Plugins run as unsandboxed code
inside `omarchy-shell`; review the checkout before enabling it.

### Update

```bash
omarchy plugin update anothadev.eglo-light
```

For a manual checkout, `git pull` in the plugin folder; the shell reloads the
plugin on its own. A changed `requirements.txt` is applied the next time the
panel is opened.

## Settings

Stored on the widget entry in `~/.config/omarchy/shell.json` and editable
with `omarchy bar set anothadev.eglo-light <key> <value>`:

| Key | Meaning |
|---|---|
| `name` | Label shown in the panel |
| `mac` | Lamp Bluetooth address (set from the panel) |
| `meshName`, `meshPassword` | Mesh credentials (set from the panel) |
| `pollIntervalSec` | Background state poll in seconds, default 20 |

For an app-managed lamp, pick it in the panel and then set the credentials
from your AwoX account:

```bash
omarchy bar set anothadev.eglo-light meshName "<mesh name>"
omarchy bar set anothadev.eglo-light meshPassword "<mesh password>"
```

Tools such as [awoxble2mqtt-api](https://github.com/BastiAKA/awoxble2mqtt-api)
or [home-assistant-awox](https://github.com/fsaris/home-assistant-awox) can
export them from an AwoX account. One widget controls one lamp; support for
several lamps is planned.

## Keybindings and scripting

The panel registers the IPC target `anothadev.eglo-light`:

```lua
-- ~/.config/hypr/bindings.lua
o.bind("SUPER + SHIFT + L", "Toggle lamp", "omarchy-shell anothadev.eglo-light toggleLight")
o.bind("SUPER + ALT + L",   "Lamp panel",  "omarchy-shell anothadev.eglo-light toggle")
```

Methods: `toggleLight`, `on`, `off`, `brightness <0-100>`, `color <#rrggbb>`,
`refresh`, `status`, and `open`/`close`/`toggle` for the panel.

There is also a command-line client for scripts:

```bash
lightctl=~/.config/omarchy/plugins/anothadev.eglo-light/bin/lightctl
$lightctl scan                                     # lamps in range and their mesh

export LIGHT_MAC=A4:C1:38:.. MESH_NAME=R-XXXXXX MESH_PASSWORD=1234
$lightctl toggle
$lightctl color '#ff8000' 60                       # colour + brightness %
$lightctl white 80 70                              # brightness %, warmth %
$lightctl preset 0                                 # built-in colour sequence
$lightctl stop                                     # stop the background daemon
```

Pass the lamp identity through those environment variables rather than the
equivalent `--mac` / `--mesh-name` / `--mesh-password` options: options are
visible to every local user through `ps`. `cron` and `at` jobs must also set
`XDG_RUNTIME_DIR=/run/user/$UID`; the plugin refuses to run without it.

## How it works

Eglo Connect lamps use the Telink BLE mesh protocol. Any BLE central can
connect to the lamp's GATT server at any time; what the mesh calls pairing is
an application-level login, an AES challenge/response keyed on the mesh name
XOR mesh password. The lamp advertises its mesh name as its Bluetooth name,
and remote-paired and factory-fresh meshes use the fixed password `1234`.

The lamp also broadcasts its live state (power, mode, brightness, warmth,
RGB) in its BLE advertisements, so state is read passively.

```
Panel.qml ──lightctl──▶ awoxlight.daemon ──BLE──▶ lamp
 (bar UI)   (unix socket)  scans beacons,
                           holds the link
```

A BLE connect costs 2 to 4 s while a command on an open link takes about
100 ms, so the daemon holds the link. A lamp freezes its beacon while a
central is connected, so every 90 s of idle time the daemon drops the link for
a few seconds to pick up a fresh beacon. That is how changes made with the
remote or a wall switch are noticed, with up to that much delay.

The daemon starts on demand and exits after ten minutes without requests.
`awoxlight/` is a bleak (BlueZ) port of the protocol documented in
[python-awox-mesh-light](https://github.com/Leiaz/python-awox-mesh-light).

## Security

- The plugin runs entirely as your user: no sudo, no pkexec, no system
  services, no privileged helper.
- Network is used once, at first run, to fetch the pinned and hash-verified
  Python packages listed above. Nothing else ever leaves the machine.
- The daemon listens on a Unix socket, mode 0600, inside `$XDG_RUNTIME_DIR`
  only. It refuses to run without that directory and never falls back to
  `/tmp`. Every request has a time budget and shutdown is bounded.
- Mesh credentials live in `~/.config/omarchy/shell.json` (mode 0600, written
  by the shell) and reach the daemon through the process environment, never
  through command-line arguments.
- Bluetooth advertisements are unauthenticated by design. Anyone in radio
  range can advertise fake lamps or spoof a lamp's state; the plugin caps what
  it remembers and shows (64 advertisers, 24 rows) so a flood cannot stall the
  shell, but it cannot tell a spoofed beacon from a real one.
- Remote-paired and factory-fresh meshes use the fixed password `1234`. That
  is a property of the product line, not of this plugin: anyone in range can
  control such a lamp with any AwoX client.
- Lamp names from the air are rendered as plain text and quoted before they
  reach `omarchy-bar set`.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Files

| Path | Purpose |
|---|---|
| `~/.config/omarchy/shell.json` | Widget entry with your lamp's address and mesh credentials (written by the shell) |
| `~/.local/share/eglo-light/venv/` | Private Python virtualenv with the pinned dependencies |
| `~/.local/share/eglo-light/install.log`, `install.lock`, `install.failed` | First-run installer log, lock and failure marker |
| `$XDG_RUNTIME_DIR/eglo-light.sock`, `.lock`, `.log` | Daemon socket, single-instance lock and rotating log (gone at logout) |

## Remove

```bash
~/.config/omarchy/plugins/anothadev.eglo-light/bin/lightctl stop
omarchy plugin remove anothadev.eglo-light
rm -rf ~/.local/share/eglo-light
```

`omarchy plugin remove` unloads the widget, drops its bar entry together with
the stored lamp settings, and deletes the checkout. The daemon exits on its
own after ten minutes if you skip the first line. For a manual install, run
`omarchy-shell shell setPluginEnabled anothadev.eglo-light false`, then delete
the plugin folder. Nothing outside the paths listed above is touched.

## Test

```bash
tests/run.sh
```

The script creates a throwaway virtualenv under `.venv/` with the pinned
runtime dependencies plus pytest. The suite runs without a lamp or Bluetooth: protocol known-answer vectors,
advertisement parsing, the device table, scan caps, socket shutdown bounds,
the launcher's install recovery, and the credential paths.

## Troubleshooting

- **"Not in range or switched off"**: the lamp has not been heard for a
  while. Bluetooth range is the main limit; the lamp must be powered at the
  wall.
- **"Mesh credentials rejected"**: the lamp was re-paired (its advertised
  `R-` name changed). Press `c` in the panel and pick it again.
- **"Bluetooth is off"**: `omarchy toggle bluetooth`, or check `bluetoothctl show`.
- **"Installing Bluetooth support…" for long**: see
  `~/.local/share/eglo-light/install.log`. An interrupted install recovers on
  the next launch and a failed one retries after ten minutes; deleting
  `~/.local/share/eglo-light` is the manual reset.

## License

MIT. See [LICENSE](LICENSE).
