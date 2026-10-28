import pathlib
import sys
import threading

PKG = pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers"
sys.path.insert(0, str(PKG))
import decision_monitor  # noqa: E402


def _files(instance):
    try:
        return sorted(
            path.name for path in (pathlib.Path(instance.control_root) / ".mw").iterdir()
        )
    except OSError as exc:
        return [f"<error {exc}>"]


_original_stop = decision_monitor.MonitorInstance.stop
_original_remove = decision_monitor.MonitorInstance._remove_own_files


def _remove(self):
    print("REMOVE enter", threading.current_thread().name, _files(self), flush=True)
    _original_remove(self)
    print("REMOVE exit ", threading.current_thread().name, _files(self), flush=True)


def _stop(self):
    print(
        "STOP enter",
        threading.current_thread().name,
        "stopped=",
        self._stopped,
        "identity=",
        None if self.identity is None else self.identity.instance_id,
        flush=True,
    )
    _original_stop(self)
    print("STOP exit ", threading.current_thread().name, _files(self), flush=True)


decision_monitor.MonitorInstance._remove_own_files = _remove
decision_monitor.MonitorInstance.stop = _stop
raise SystemExit(decision_monitor.serve(pathlib.Path(sys.argv[1])))
