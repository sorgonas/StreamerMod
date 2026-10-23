"""Session-scoped KDE idle inhibition, run with Debian's system Python.

The private D-Bus connection owns all inhibitions. Closing it, including process
termination, releases them. No desktop settings are rewritten.
"""
import argparse
import signal
import time
from pathlib import Path


def process_identity(pid):
    try:
        # Field 22 is the start time. Checking it prevents a reused PID from
        # accidentally keeping the desktop awake after Sorgobot has exited.
        return (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def hold(pid):
    import dbus

    identity = process_identity(pid)
    if identity is None:
        return
    bus = dbus.SessionBus(private=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        app = 'Sorgobot Studio'
        reason = 'Sorgobot ist geöffnet: Bildschirm und Testbetrieb aktiv halten'
        locker = dbus.Interface(bus.get_object('org.freedesktop.ScreenSaver', '/ScreenSaver'),
                                'org.freedesktop.ScreenSaver')
        locker.Inhibit(app, reason)
        power = dbus.Interface(bus.get_object('org.kde.Solid.PowerManagement',
                               '/org/kde/Solid/PowerManagement/PolicyAgent'),
                               'org.kde.Solid.PowerManagement.PolicyAgent')
        # KDE ChangeScreenSettings=4 also implies InterruptSession=1.
        # https://github.com/KDE/powerdevil/blob/master/daemon/powerdevilpolicyagent.h
        power.AddInhibition(dbus.UInt32(4), app, reason)
        print('Wachhalten aktiv: automatische Sperre, Bildschirmabschaltung und Standby pausiert.', flush=True)
        while not stopping and process_identity(pid) == identity:
            time.sleep(1)
    finally:
        bus.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch-pid', type=int, required=True)
    args = parser.parse_args()
    try:
        hold(args.watch_pid)
    except Exception as exc:
        raise SystemExit('Wachhalten nicht verfügbar: '+str(exc))
