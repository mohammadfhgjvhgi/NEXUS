import subprocess
import sys


def test_spawn_bg_worker() -> None:
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        [sys.executable, r"M:\NEXUS\_bg_extract_worker.py"],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
