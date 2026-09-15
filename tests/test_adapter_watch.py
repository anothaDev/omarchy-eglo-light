"""The scan watchdog must notice the Bluetooth adapter going away and coming back."""
import asyncio

from awoxlight import daemon as D


class _Scanner:
    def __init__(self):
        self.started = 0

    async def start(self):
        self.started += 1

    async def stop(self):
        pass


def _run(powered_sequence, ticks=6):
    """Drive scan_watchdog for a few ticks; the adapter reports the readings
    in order and then keeps repeating the last one, like a real adapter."""
    async def go():
        d = D.Daemon()
        readings = list(powered_sequence)
        state = {"powered": readings[0], "calls": 0}

        async def fake_powered():
            state["calls"] += 1
            if readings:
                state["powered"] = readings.pop(0)
            return state["powered"]

        d.adapter_powered = fake_powered

        async def fake_start():  # a real scan only starts on a powered adapter
            async with d.scan_lock:
                if d.scanner is None and state["powered"]:
                    d.scanner = _Scanner()
                    d.bluetooth_ok = True
                    d.bluetooth_error = ""
        d.start_scan = fake_start
        real_sleep = asyncio.sleep

        async def quick_sleep(_):
            await real_sleep(0)
        D.asyncio.sleep = quick_sleep
        try:
            task = asyncio.create_task(d.scan_watchdog())
            while state["calls"] < ticks:
                await real_sleep(0.01)
            d.stopping.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            D.asyncio.sleep = real_sleep
        return d, None
    return asyncio.run(go())


def test_adapter_off_is_reported_and_scan_stopped():
    d, flags = _run([False, False])
    assert d.bluetooth_ok is False
    assert d.bluetooth_error == "Bluetooth is off"
    assert d.scanner is None


def test_adapter_back_restarts_scan():
    d, flags = _run([False, True, True])
    assert d.bluetooth_ok is True
    assert d.bluetooth_error == ""
    assert d.scanner is not None


def test_unreachable_bluez_keeps_previous_state():
    d, _ = _run([None, None])
    assert d.bluetooth_ok is True  # no verdict, no false alarm
