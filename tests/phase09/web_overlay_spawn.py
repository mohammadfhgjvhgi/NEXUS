import subprocess, sys
_DETACHED = 0x00000008 | 0x00000200 | 0x01000000
proc = subprocess.Popen(
    [sys.executable, "-u", r"M:\NEXUS\proofs\web_overlay_daemon.py"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=_DETACHED, close_fds=True)
print("daemon pid:", proc.pid)
