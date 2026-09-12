# Security Policy

## Supported versions

Security fixes are provided for the latest released version.

## Reporting

Use **Report a vulnerability** in the repository's Security tab to open a
private security advisory. Do not put vulnerability details in a public
issue. Include the plugin version, reproduction steps and impact.

## Trust model

- The plugin runs as the desktop user inside `omarchy-shell` plus a per-user
  background daemon. There is no privileged helper, no sudo or pkexec, no
  system service and no network listener.
- Network access happens once, at first run, to install the Python packages
  pinned by version and SHA-256 hash in `requirements.txt`. A changed pin
  requires a new release.
- The daemon's Unix socket, lock and log live only in `$XDG_RUNTIME_DIR`
  (mode 0600, owner-verified); the plugin refuses to run without it.
- Other processes running as the same user are outside the trust boundary:
  they can read the widget settings, talk to the socket or stop the daemon.
- Bluetooth advertisements and GATT replies are untrusted input from anyone in
  radio range. They are bounds-checked, capped (64 remembered advertisers, 24
  listed rows, 1 MB replies), rendered as plain text and shell-quoted before
  reaching `omarchy-bar set`. Spoofed beacons cannot be distinguished from real
  ones; that is inherent to the protocol.
- Mesh credentials for remote-paired and factory-fresh lamps are the product
  line's fixed defaults. App-managed lamp credentials are stored in
  `~/.config/omarchy/shell.json` (mode 0600) and passed to the daemon through
  the environment, never through command-line arguments.

## Limits

| Surface | Bound |
|---|---|
| Socket request line | 64 KiB, then the connection is closed |
| `scan` wait | 0 to 30 s |
| Advertisers remembered / listed | 64 / 24 |
| Client reply | 1 MB, 30 s total |
| Registered lamps | 16, least recently used evicted |
| Shutdown | about 5 s worst case; a second SIGTERM exits immediately |
| Daemon lifetime | exits after 10 min without requests |

A full pre-publish review with findings, fixes and the maintainer sign-off
checklist was done against the 0.2.0 tree; the eight findings it produced are
fixed in the published revision.
