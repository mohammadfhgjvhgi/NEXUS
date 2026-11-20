import tarfile
import time
import traceback
from pathlib import Path

LOG = Path(r"M:\NEXUS\_bg_extract.log")


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")


try:
    log("WORKER START")
    src = Path(r"M:\NEXUS\models\whisper-tiny.tar.bz2")
    dst = Path(r"M:\NEXUS\models")
    with tarfile.open(src, "r:bz2") as tf:
        for m in tf.getmembers():
            t0 = time.monotonic()
            tf.extract(m, path=str(dst))
            log(f"DONE {m.name} {m.size}B in {time.monotonic() - t0:.1f}s")
    log("WORKER ALL DONE")
except Exception:
    log("WORKER FAIL: " + traceback.format_exc()[-800:])
