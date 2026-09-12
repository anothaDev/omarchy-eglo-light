import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Eglo Connect / AwoX mesh lamp in the bar.
//
// State comes from the lamp's own BLE beacons, read by the lightctl daemon;
// actions go out through `lightctl`, which holds a Bluetooth link so commands
// land in ~100 ms. The lamp identity (address + mesh credentials) lives in this
// widget's settings and is filled in from the panel's own setup scan.
Panel {
  id: root
  moduleName: "anothadev.eglo-light"
  ipcTarget: "anothadev.eglo-light"
  manageIpc: false

  readonly property string ctl: String(Qt.resolvedUrl("bin/lightctl")).replace(/^file:\/\//, "")
  // The plugin directory name is the plugin id, also for clones, so settings
  // written back land on the right widget entry.
  readonly property string pluginId: {
    var dir = String(Qt.resolvedUrl(".")).replace(/\/+$/, "")
    return dir.substring(dir.lastIndexOf("/") + 1) || moduleName
  }

  // ---- settings ----
  readonly property string mac: String(setting("mac", "")).toUpperCase()
  readonly property string meshName: String(setting("meshName", ""))
  readonly property string meshPassword: String(setting("meshPassword", ""))
  readonly property string lampName: String(setting("name", "")) || "Lamp"
  readonly property int pollIntervalSec: Math.max(5, parseInt(setting("pollIntervalSec", 20), 10) || 20)
  readonly property bool configured: mac !== ""
  // Credentials go through the environment, never argv: a command line is
  // world-readable in /proc/<pid>/cmdline and `ps` on a multi-user host.
  readonly property var lampEnv: ({ LIGHT_MAC: mac, MESH_NAME: meshName, MESH_PASSWORD: meshPassword })

  // ---- lamp state (from the daemon) ----
  property bool available: false
  property bool lampOn: false
  property string mode: "white"       // "white" | "color"
  property int brightness: 100        // 1..100
  property int temp: 50               // 0 cold .. 100 warm
  property var rgb: [255, 255, 255]
  property string lampError: ""       // from the daemon: "lamp not reachable", "mesh credentials rejected", …
  property bool bluetoothOk: true
  property bool installing: false
  property string installError: ""
  property bool everPolled: false
  // Capabilities from the product id in the lamp's beacon (see awoxlight/devices.py).
  property var device: null
  readonly property bool hasColor: device ? device.color === true : true
  readonly property bool hasTemp: device ? device.temperature === true : true
  readonly property bool hasBrightness: device ? device.brightness === true : true
  readonly property string modelName: device && device.known ? String(device.name) : ""

  // Optimistic power state: -1 follow the lamp, 0/1 while a toggle lands.
  property int desiredPower: -1
  property var queuedAction: null
  readonly property bool busy: actionProc.running

  // ---- setup scan ----
  property var foundLamps: []
  property bool scanning: scanProc.running
  property bool scannedOnce: false
  property string scanError: ""

  readonly property bool isOn: desiredPower === -1 ? lampOn : desiredPower === 1
  readonly property bool controlsEnabled: configured && bluetoothOk && lampError === "" && available
  readonly property color rgbColor: Qt.rgba(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1)
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color hoverFill: bar ? Style.hoverFillFor(bar.foreground, Color.accent) : "transparent"
  readonly property color selectedFill: bar ? Style.selectedFillFor(bar.foreground, Color.accent) : "transparent"
  readonly property color lampColor: !isOn || !controlsEnabled ? dim : (mode === "color" ? rgbColor : whiteTint(temp))
  readonly property color barIconColor: !isOn || !controlsEnabled ? Qt.darker(barForeground, 1.55) : (mode === "color" ? rgbColor : barForeground)
  readonly property string glyph: {
    if (!configured) return "󱩎"
    if (!bluetoothOk || lampError !== "") return "󰌵"
    return isOn ? "󰌵" : "󰌶"
  }
  readonly property string statusText: {
    if (installing) return "Installing Bluetooth support…"
    if (installError !== "") return installError
    if (!configured) return "No lamp configured"
    if (!everPolled) return "Checking…"
    if (!bluetoothOk) return "Bluetooth is off"
    if (lampError === "mesh credentials rejected") return "Mesh credentials rejected"
    if (lampError === "no mesh credentials") return "Mesh credentials needed"
    if (!available || lampError === "lamp not reachable") return "Not in range or switched off"
    if (lampError !== "") return lampError
    if (!isOn) return "Off"
    if (!hasBrightness) return "On"
    if (mode === "color" && hasColor) return "Colour · " + brightness + "%"
    if (!hasTemp) return "On · " + brightness + "%"
    return whiteName(temp) + " · " + brightness + "%"
  }
  readonly property string hintText: {
    if (!configured) return scanning ? "Listening for lamps…" : (scannedOnce && foundLamps.length === 0 ? "No lamps heard. Power one on within a few metres and scan again." : "Pick your lamp below. A lamp paired to the Eglo remote works out of the box.")
    if (!bluetoothOk) return "Turn Bluetooth on to control the lamp."
    if (lampError === "mesh credentials rejected") return "The lamp was re-paired. Run setup again (c) or set meshName/meshPassword in the widget settings."
    if (lampError === "no mesh credentials") return "This lamp uses an app mesh. Set meshName and meshPassword from your AwoX account in the widget settings."
    return ""
  }
  readonly property string toggleHint: isOn ? "Turn " + lampName + " off" : "Turn " + lampName + " on"

  readonly property var allSwatches: [
    { name: "Warm",    kind: "white",  temp: 100, fill: "#ffb56b" },
    { name: "Soft",    kind: "white",  temp: 65,  fill: "#ffd9a6" },
    { name: "Neutral", kind: "white",  temp: 30,  fill: "#fff3dd" },
    { name: "Cool",    kind: "white",  temp: 0,   fill: "#d6ecff" },
    { name: "Red",     kind: "color",  rgb: [255, 0, 0],    fill: "#ff3030" },
    { name: "Orange",  kind: "color",  rgb: [255, 96, 0],   fill: "#ff7a1a" },
    { name: "Yellow",  kind: "color",  rgb: [255, 210, 0],  fill: "#ffd21a" },
    { name: "Green",   kind: "color",  rgb: [0, 255, 64],   fill: "#2ee85a" },
    { name: "Cyan",    kind: "color",  rgb: [0, 220, 255],  fill: "#2ad6ff" },
    { name: "Blue",    kind: "color",  rgb: [0, 70, 255],   fill: "#2e6bff" },
    { name: "Purple",  kind: "color",  rgb: [150, 0, 255],  fill: "#a24dff" },
    { name: "Pink",    kind: "color",  rgb: [255, 0, 150],  fill: "#ff3fa6" },
    { name: "Party",   kind: "preset", value: 0,            fill: "transparent", glyph: "󱁖" }
  ]
  // A tunable-white lamp still gets the white presets; a colour lamp gets everything.
  readonly property var swatches: hasColor ? allSwatches : allSwatches.filter(function(s) { return s.kind === "white" })

  // ---- keyboard cursor ----
  // Control mode: header (switch) → brightness → warmth → swatches.
  // Setup mode: the found-lamp list, plus the rescan button as the last row.
  property string focusSection: "header"
  property int swatchIndex: 0
  property int lampIndex: 0
  property bool cursorActive: false
  property real wheelAccumulator: 0
  readonly property bool headerHasCursor: cursorActive && focusSection === "header"
  readonly property var sections: {
    var list = ["header"]
    if (hasBrightness) list.push("brightness")
    if (hasTemp) list.push("warmth")
    if (hasTemp || hasColor) list.push("swatches")
    return list
  }

  function whiteTint(t) {
    var w = Math.max(0, Math.min(100, t)) / 100
    return Qt.rgba(1, 0.97 - 0.22 * w, 0.92 - 0.5 * w, 1)
  }

  function whiteName(t) {
    if (t >= 80) return "Warm white"
    if (t >= 55) return "Soft white"
    if (t >= 25) return "Neutral white"
    return "Cool white"
  }

  function swatchIsCurrent(s) {
    if (!isOn) return false
    if (s.kind === "white") return mode === "white" && Math.abs(temp - s.temp) <= 12
    if (s.kind === "color") return mode === "color" && rgb[0] === s.rgb[0] && rgb[1] === s.rgb[1] && rgb[2] === s.rgb[2]
    return false
  }

  function kindLabel(kind) {
    if (kind === "remote") return "paired to remote"
    if (kind === "unpaired") return "factory fresh"
    return "app mesh"
  }

  // ---- daemon I/O ----
  function parseReply(raw) {
    var text = String(raw || "").trim()
    if (text === "") return null
    try { return JSON.parse(text) } catch (e) { return null }
  }

  function applyReply(raw) {
    // Bound the work before parsing: the reply crosses from radio range.
    if (String(raw || "").length > 65536) { lampError = "reply too large"; return }
    var reply = parseReply(raw)
    if (!reply) return
    if (reply.installing) { installing = true; return }
    installing = false
    if (reply.failed) { installError = String(reply.error || "setup failed"); return }
    installError = ""
    everPolled = true
    var st = reply.state
    if (!st) {
      if (reply.ok === false && reply.error) lampError = String(reply.error)
      return
    }
    bluetoothOk = st.bluetooth !== false
    lampError = String(st.error || "")
    available = st.available === true
    if (st.device) device = st.device
    if (!("on" in st)) return
    lampOn = st.on === true
    mode = String(st.mode || "white")
    if (!brightnessSlider.dragging && !brightnessDebounce.running) brightness = Math.max(1, Math.min(100, parseInt(st.brightness, 10) || 1))
    if (!warmthSlider.dragging && !warmthDebounce.running) temp = Math.max(0, Math.min(100, parseInt(st.temp, 10) || 0))
    if (st.rgb && st.rgb.length === 3) rgb = [st.rgb[0], st.rgb[1], st.rgb[2]]
    if (desiredPower !== -1 && lampOn === (desiredPower === 1)) desiredPower = -1
  }

  function refresh() {
    if (!configured) return
    if (statusProc.running) return
    statusProc.command = [ctl, "status", "--json"]
    statusProc.running = true
  }

  function runAction(args) {
    if (!configured) return
    if (actionProc.running) { queuedAction = args; return }
    actionProc.command = [ctl].concat(args, ["--json"])
    actionProc.running = true
  }

  function setPower(on) {
    desiredPower = on ? 1 : 0
    powerSettle.restart()
    runAction([on ? "on" : "off"])
  }

  function toggleLight() { if (controlsEnabled || !everPolled) setPower(!isOn) }

  function setBrightness(value, immediate) {
    brightness = Math.max(1, Math.min(100, Math.round(value)))
    if (immediate) { brightnessDebounce.stop(); runAction(["brightness", String(brightness)]) }
    else brightnessDebounce.restart()
  }

  function setWarmth(value, immediate) {
    temp = Math.max(0, Math.min(100, Math.round(value)))
    mode = "white"
    if (immediate) { warmthDebounce.stop(); runAction(["temp", String(temp)]) }
    else warmthDebounce.restart()
  }

  function applySwatch(index) {
    var s = swatches[Math.max(0, Math.min(swatches.length - 1, index))]
    if (!s) return
    desiredPower = 1
    powerSettle.restart()
    if (s.kind === "white") { mode = "white"; temp = s.temp; runAction(["white", String(brightness), String(s.temp)]) }
    else if (s.kind === "color") { mode = "color"; rgb = s.rgb; runAction(["color", String(s.rgb[0]), String(s.rgb[1]), String(s.rgb[2])]) }
    else runAction(["preset", String(s.value)])
  }

  // ---- setup ----
  function startScan() {
    if (scanProc.running) return
    scanError = ""
    scanProc.running = true
  }

  function applyScanReply(raw) {
    scannedOnce = true
    // Bound the work before parsing: anyone in radio range can fill a scan.
    if (String(raw || "").length > 262144) { scanError = "scan reply too large"; return }
    var reply = parseReply(raw)
    if (!reply) { scanError = "scan failed"; return }
    if (reply.installing) { installing = true; return }
    installing = false
    if (reply.failed) { installError = String(reply.error || "setup failed"); return }
    if (reply.bluetooth === false) { bluetoothOk = false; scanError = "Bluetooth is off"; return }
    bluetoothOk = true
    if (reply.ok === false) { scanError = String(reply.error || "scan failed"); return }
    foundLamps = (reply.lamps || []).slice(0, 24)
    lampIndex = Math.min(lampIndex, Math.max(0, foundLamps.length - 1))
  }

  function setWidgetSettings(values) {
    // `omarchy-bar set <pluginId> ...` has no placement selector: it resolves to
    // the first bar entry with this id. That is why the manifest sets
    // allowMultiple: false - a second instance would rewrite the first one's lamp.
    // One shell invocation so the sequential writes to shell.json cannot race.
    var parts = []
    for (var key in values) {
      parts.push("omarchy-bar set " + Util.shellQuote(pluginId) + " " + Util.shellQuote(key) + " " + Util.shellQuote(String(values[key])))
    }
    Quickshell.execDetached(["bash", "-c", parts.join(" && ")])
  }

  function chooseLamp(index) {
    var lamp = foundLamps[index]
    if (!lamp) return
    var name = lamp.name || ""
    setWidgetSettings({
      mac: lamp.mac,
      meshName: lamp.mesh_name || "",
      meshPassword: lamp.mesh_password || "",
      name: lampName === "Lamp" || String(setting("name", "")) === "" ? (lamp.kind === "remote" ? "Lamp" : name || "Lamp") : String(setting("name", ""))
    })
    everPolled = false
    lampError = ""
  }

  function forgetLamp() {
    setWidgetSettings({ mac: "", meshName: "", meshPassword: "" })
    everPolled = false
    lampError = ""
    foundLamps = []
    scannedOnce = false
  }

  // ---- cursor movement ----
  function moveCursor(dy) {
    if (!configured) {
      var rows = foundLamps.length + 1 // + rescan button
      lampIndex = Math.max(0, Math.min(rows - 1, lampIndex + dy))
      return
    }
    var i = sections.indexOf(focusSection)
    if (i < 0) i = 0
    i = Math.max(0, Math.min(sections.length - 1, i + dy))
    focusSection = sections[i]
  }

  function moveCursorH(dx) {
    if (!configured) return
    if (focusSection === "brightness") setBrightness(brightness + dx * 5, false)
    else if (focusSection === "warmth") setWarmth(temp + dx * 10, false)
    else if (focusSection === "swatches") swatchIndex = Math.max(0, Math.min(swatches.length - 1, swatchIndex + dx))
  }

  function activateCursor() {
    if (!configured) {
      if (lampIndex >= foundLamps.length) startScan()
      else chooseLamp(lampIndex)
      return
    }
    if (focusSection === "header") toggleLight()
    else if (focusSection === "swatches") applySwatch(swatchIndex)
    else if (focusSection === "brightness") setBrightness(brightness, true)
    else if (focusSection === "warmth") setWarmth(temp, true)
  }

  function setHeaderCursor() {
    cursorActive = true
    focusSection = "header"
  }

  onOpenedChanged: {
    if (opened) {
      cursorActive = false
      focusSection = "header"
      if (configured) refresh()
      else if (!scannedOnce) startScan()
    }
  }

  onConfiguredChanged: {
    everPolled = false
    lampError = ""
    if (configured) refresh()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Timer {
    interval: root.installing ? 3000 : (root.opened ? 2500 : root.pollIntervalSec * 1000)
    running: root.configured
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  // Give a power command a few seconds to be confirmed, then trust the lamp again.
  Timer {
    id: powerSettle
    interval: 8000
    repeat: false
    onTriggered: root.desiredPower = -1
  }

  Timer {
    id: brightnessDebounce
    interval: 160
    repeat: false
    onTriggered: root.runAction(["brightness", String(root.brightness)])
  }

  Timer {
    id: warmthDebounce
    interval: 160
    repeat: false
    onTriggered: root.runAction(["temp", String(root.temp)])
  }

  Process {
    id: statusProc
    running: false
    command: []
    environment: root.lampEnv
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    onExited: function(exitCode) {
      var text = String(statusOut.text || "").trim()
      if (text === "") {
        root.everPolled = true
        root.available = false
        root.lampError = exitCode === 0 ? "" : "lightctl failed"
        return
      }
      root.applyReply(text)
    }
  }

  Process {
    id: actionProc
    running: false
    command: []
    environment: root.lampEnv
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    onExited: function(exitCode) {
      root.applyReply(actionOut.text)
      if (root.queuedAction) {
        var next = root.queuedAction
        root.queuedAction = null
        root.runAction(next)
      }
    }
  }

  Process {
    id: scanProc
    running: false
    command: [root.ctl, "scan", "--json", "--wait", "6"]
    stdout: StdioCollector { id: scanOut; waitForEnd: true }
    onExited: function(exitCode) { root.applyScanReply(scanOut.text) }
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function toggleLight(): string { root.toggleLight(); return "ok" }
    function on(): string { root.setPower(true); return "ok" }
    function off(): string { root.setPower(false); return "ok" }
    function brightness(percent: string): string { root.setBrightness(parseInt(percent, 10), true); return "ok" }
    function color(hex: string): string {
      var h = String(hex).replace("#", "")
      if (h.length !== 6) return "expected #rrggbb"
      root.rgb = [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)]
      root.mode = "color"
      root.runAction(["color", String(root.rgb[0]), String(root.rgb[1]), String(root.rgb[2])])
      return "ok"
    }
    function refresh(): string { root.refresh(); return "ok" }
    function status(): string { return root.statusText }
  }

  // ---- bar button ----
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.glyph
    active: root.isOn && root.controlsEnabled
    useActiveColor: true
    activeColor: root.barIconColor
    dimmed: !root.isOn || !root.controlsEnabled
    tooltipText: root.lampName + ": " + root.statusText
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.toggleLight()
      else if (buttonCode === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
    onWheelMoved: function(delta) {
      var wheel = Util.wheelSteps(root.wheelAccumulator, delta)
      root.wheelAccumulator = wheel.remainder
      if (wheel.steps === 0 || !root.isOn || !root.controlsEnabled) return
      root.setBrightness(root.brightness + wheel.steps * 5, false)
    }
  }

  // ---- popup ----
  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(340))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        if (dy !== 0) root.moveCursor(dy)
        else if (dx !== 0) root.moveCursorH(dx)
      }
      onActivateRequested: if (root.cursorActive) root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "t" || t === "T") root.toggleLight()
        else if (t === "r" || t === "R") { if (root.configured) root.refresh(); else root.startScan() }
        else if (t === "c" || t === "C") { if (root.configured) root.forgetLamp() }
      }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(12)

        // ---------- Hero ----------
        Item {
          id: header
          width: parent.width
          implicitHeight: hero.implicitHeight
          readonly property bool ringVisible: root.headerHasCursor && root.configured
          function focusHero() { root.setHeaderCursor() }

          PanelHero {
            id: hero
            width: parent.width
            title: root.configured ? root.lampName : "Eglo / AwoX lamp"
            meta: root.statusText
            detail: root.configured ? (root.modelName !== "" ? root.modelName : root.mac.substr(-8)) : ""
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.isOn && root.controlsEnabled ? 1.0 : 0.6
            iconComponent: Component {
              Text {
                textFormat: Text.PlainText
                text: root.glyph
                color: root.lampColor
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
            trailingControl: Component {
              ToggleSwitch {
                id: powerSwitch
                visible: root.configured
                enabled: root.controlsEnabled
                opacity: root.controlsEnabled ? 1.0 : 0.4
                checked: root.isOn
                busy: root.busy && root.desiredPower !== -1
                hasCursor: header.ringVisible
                foreground: hero.foreground
                onHovered: function(on) { if (on) header.focusHero() }
                onToggled: root.toggleLight()

                PanelToolTip {
                  visible: powerSwitch.containsMouse
                  text: root.toggleHint
                  fontFamily: hero.fontFamily
                }
              }
            }
          }
        }

        Text {
          visible: root.hintText !== ""
          width: parent.width
          textFormat: Text.PlainText
          text: root.hintText
          color: root.lampError !== "" || !root.bluetoothOk ? root.urgent : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        PanelSeparator { width: parent.width; foreground: root.foreground }

        // ================= Setup: pick a lamp =================
        Column {
          visible: !root.configured
          width: parent.width
          spacing: Style.space(6)

          Item {
            width: parent.width
            implicitHeight: Math.max(lampsHeader.implicitHeight, scanSpinner.implicitHeight)

            PanelSectionHeader {
              id: lampsHeader
              text: "LAMPS NEARBY"
              foreground: root.foreground
              fontFamily: root.fontFamily
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
            }

            Text {
              id: scanSpinner
              textFormat: Text.PlainText
              text: root.scanning ? "scanning…" : (root.scanError !== "" ? root.scanError : root.foundLamps.length + " found")
              color: root.scanError !== "" ? root.urgent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
            }
          }

          Repeater {
            model: root.foundLamps.length

            Rectangle {
              id: lampRow
              required property int index
              readonly property var lamp: root.foundLamps[index]
              readonly property bool hasCursor: root.cursorActive && root.lampIndex === index
              width: parent.width
              implicitHeight: lampInner.implicitHeight + Style.spacing.rowPaddingX
              radius: Style.cornerRadius
              color: hasCursor ? root.selectedFill : (rowHover.hovered ? root.hoverFill : "transparent")

              Row {
                id: lampInner
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: Style.space(8)
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(10)

                Text {
                  textFormat: Text.PlainText
                  text: "󰌵"
                  color: lampRow.lamp.kind === "app" ? root.dim : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.icon
                  anchors.verticalCenter: parent.verticalCenter
                }

                Column {
                  width: parent.width - Style.space(10) * 2 - Style.font.icon - rssiText.implicitWidth
                  spacing: Style.space(1)
                  anchors.verticalCenter: parent.verticalCenter

                  Text {
                    textFormat: Text.PlainText
                    text: (lampRow.lamp.name || "Unnamed lamp") + "  ·  " + lampRow.lamp.mac
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    elide: Text.ElideRight
                    width: parent.width
                  }

                  Text {
                    textFormat: Text.PlainText
                    text: (lampRow.lamp.known ? lampRow.lamp.product + " · " : "") + root.kindLabel(lampRow.lamp.kind) + (lampRow.lamp.kind === "app" ? " · needs credentials" : "")
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                    width: parent.width
                  }
                }

                Text {
                  id: rssiText
                  textFormat: Text.PlainText
                  text: lampRow.lamp.rssi + " dBm"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  anchors.verticalCenter: parent.verticalCenter
                }
              }

              HoverHandler {
                id: rowHover
                onHoveredChanged: if (hovered) { root.cursorActive = true; root.lampIndex = lampRow.index }
              }

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.chooseLamp(lampRow.index)
              }
            }
          }

          Rectangle {
            id: rescanRow
            readonly property bool hasCursor: root.cursorActive && root.lampIndex >= root.foundLamps.length
            width: parent.width
            implicitHeight: rescanText.implicitHeight + Style.spacing.rowPaddingX
            radius: Style.cornerRadius
            color: hasCursor ? root.selectedFill : (rescanHover.hovered ? root.hoverFill : "transparent")

            Text {
              id: rescanText
              anchors.left: parent.left
              anchors.leftMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              textFormat: Text.PlainText
              text: root.scanning ? "󰑓  Scanning…" : "󰑓  Scan again"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
            }

            HoverHandler {
              id: rescanHover
              onHoveredChanged: if (hovered) { root.cursorActive = true; root.lampIndex = root.foundLamps.length }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.startScan()
            }
          }
        }

        // ================= Controls =================
        Column {
          visible: root.configured
          width: parent.width
          spacing: Style.space(12)

          // ---------- Brightness ----------
          Column {
            visible: root.hasBrightness
            width: parent.width
            spacing: Style.space(6)
            opacity: root.isOn && root.controlsEnabled ? 1.0 : 0.45

            Item {
              width: parent.width
              implicitHeight: Math.max(brightnessHeader.implicitHeight, brightnessValue.implicitHeight)

              PanelSectionHeader {
                id: brightnessHeader
                text: "BRIGHTNESS"
                foreground: root.foreground
                fontFamily: root.fontFamily
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: brightnessValue
                textFormat: Text.PlainText
                text: root.brightness + "%"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            Rectangle {
              width: parent.width
              height: Style.spacing.controlHeight
              radius: Style.cornerRadius
              color: root.cursorActive && root.focusSection === "brightness" ? root.selectedFill : "transparent"

              PanelSlider {
                id: brightnessSlider
                bar: root.bar
                enabled: root.controlsEnabled
                anchors.fill: parent
                anchors.leftMargin: Style.space(6)
                anchors.rightMargin: Style.space(6)
                minimum: 1
                maximum: 100
                step: 1
                integer: true
                value: root.brightness
                onMoved: function(v) { root.setBrightness(v, false) }
                onReleased: function(v) { root.setBrightness(v, true) }
              }

              HoverHandler {
                onHoveredChanged: if (hovered) { root.cursorActive = true; root.focusSection = "brightness" }
              }
            }
          }

          // ---------- Warmth ----------
          Column {
            visible: root.hasTemp
            width: parent.width
            spacing: Style.space(6)
            opacity: root.isOn && root.controlsEnabled ? 1.0 : 0.45

            Item {
              width: parent.width
              implicitHeight: Math.max(warmthHeader.implicitHeight, warmthValue.implicitHeight)

              PanelSectionHeader {
                id: warmthHeader
                text: "WHITE WARMTH"
                foreground: root.foreground
                fontFamily: root.fontFamily
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: warmthValue
                textFormat: Text.PlainText
                text: root.mode === "white" ? root.whiteName(root.temp) : "Colour mode"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            Rectangle {
              width: parent.width
              height: Style.spacing.controlHeight
              radius: Style.cornerRadius
              color: root.cursorActive && root.focusSection === "warmth" ? root.selectedFill : "transparent"

              Text {
                id: coldGlyph
                textFormat: Text.PlainText
                text: "󰖘"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.icon
                anchors.left: parent.left
                anchors.leftMargin: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: warmGlyph
                textFormat: Text.PlainText
                text: "󰈸"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.icon
                anchors.right: parent.right
                anchors.rightMargin: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
              }

              PanelSlider {
                id: warmthSlider
                bar: root.bar
                enabled: root.controlsEnabled
                anchors.left: coldGlyph.right
                anchors.right: warmGlyph.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: Style.space(10)
                anchors.rightMargin: Style.space(10)
                minimum: 0
                maximum: 100
                step: 1
                integer: true
                value: root.temp
                fillColor: root.whiteTint(root.temp)
                onMoved: function(v) { root.setWarmth(v, false) }
                onReleased: function(v) { root.setWarmth(v, true) }
              }

              HoverHandler {
                onHoveredChanged: if (hovered) { root.cursorActive = true; root.focusSection = "warmth" }
              }
            }
          }

          PanelSeparator { visible: root.hasTemp || root.hasColor; width: parent.width; foreground: root.foreground }

          // ---------- Colours / white presets ----------
          Column {
            visible: root.hasTemp || root.hasColor
            width: parent.width
            spacing: Style.space(8)
            opacity: root.controlsEnabled ? 1.0 : 0.45

            PanelSectionHeader {
              text: root.hasColor ? "COLOURS" : "WHITE PRESETS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Grid {
              id: swatchGrid
              width: parent.width
              columns: 7
              readonly property real cell: Math.floor(width / columns)
              rowSpacing: Style.space(4)
              columnSpacing: 0

              Repeater {
                model: root.swatches.length

                Item {
                  id: swatch
                  required property int index
                  readonly property var spec: root.swatches[index]
                  readonly property bool hasCursor: root.cursorActive && root.focusSection === "swatches" && root.swatchIndex === index
                  readonly property bool current: root.swatchIsCurrent(spec)
                  width: swatchGrid.cell
                  height: swatchGrid.cell

                  Rectangle {
                    anchors.centerIn: parent
                    width: Math.round(parent.width * 0.62)
                    height: width
                    radius: width / 2
                    color: swatch.spec.kind === "preset" ? "transparent" : swatch.spec.fill
                    border.width: swatch.hasCursor ? Math.max(2, Style.space(2)) : (swatch.current ? Math.max(1, Style.space(1)) : (swatch.spec.kind === "preset" ? 1 : 0))
                    border.color: swatch.hasCursor ? root.foreground : (swatch.current ? root.foreground : root.dim)
                    scale: swatch.hasCursor ? 1.12 : 1.0
                    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

                    Text {
                      visible: swatch.spec.kind === "preset"
                      anchors.centerIn: parent
                      textFormat: Text.PlainText
                      text: swatch.spec.glyph || ""
                      color: root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.icon
                    }
                  }

                  MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: root.controlsEnabled
                    cursorShape: Qt.PointingHandCursor
                    onEntered: { root.cursorActive = true; root.focusSection = "swatches"; root.swatchIndex = swatch.index }
                    onClicked: root.applySwatch(swatch.index)
                  }

                  PanelToolTip {
                    visible: swatch.hasCursor && root.focusSection === "swatches"
                    text: swatch.spec.name
                    fontFamily: root.fontFamily
                  }
                }
              }
            }
          }
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.configured
            ? "j/k move · h/l adjust · Enter apply · t toggle · c change lamp"
            : "j/k move · Enter choose · r scan again"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }
    }
  }
}
