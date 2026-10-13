@echo off
echo STUB_PI_SPAWNED> "H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence\runs\t08-cutover-20261012\stub\pos\spawn-marker.txt"
echo argv=%*>> "H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence\runs\t08-cutover-20261012\stub\pos\spawn-marker.txt"
echo PI_WORKER_TASK=%PI_WORKER_TASK%>> "H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence\runs\t08-cutover-20261012\stub\pos\spawn-marker.txt"
ping -n 9 127.0.0.1 >nul
exit /b 0
