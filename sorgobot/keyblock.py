"""Bounded evdev/uinput relay for X11 and Wayland. No shell or root escalation.

Requires explicit permissions for one physical keyboard and /dev/uinput.
The physical device is always released on exit, error, signal or deadline.
"""
import argparse
import select
import signal
import time


def main():
    import evdev
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True)
    parser.add_argument('--key', required=True, choices=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('Dauer muss zwischen 1 und 600 Sekunden liegen')
    blocked = getattr(evdev.ecodes, 'KEY_' + args.key)
    device = evdev.InputDevice(args.device)
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    held = set()
    try:
        with evdev.UInput.from_device(device, name='Sorgobot temporary key filter') as output:
            device.grab()
            try:
                deadline = time.monotonic() + args.seconds
                while running and time.monotonic() < deadline:
                    ready, _, _ = select.select([device.fd], [], [], min(0.2, max(0, deadline - time.monotonic())))
                    if not ready:
                        continue
                    for event in device.read():
                        if event.type == evdev.ecodes.EV_KEY and event.code == blocked:
                            continue
                        output.write_event(event)
                        if event.type == evdev.ecodes.EV_KEY:
                            if event.value == 1: held.add(event.code)
                            if event.value == 0: held.discard(event.code)
            finally:
                for key in held:
                    output.write(evdev.ecodes.EV_KEY, key, 0)
                output.syn()
                device.ungrab()
    finally:
        device.close()


if __name__ == '__main__':
    main()
