import tarfile
import time
from pathlib import Path


def test_extract_sync() -> None:
    src = Path(r"M:\NEXUS\models\whisper-tiny.tar.bz2")
    dst = Path(r"M:\NEXUS\models")
    print("TAR_EXISTS:", src.exists(), "SIZE:", src.stat().st_size if src.exists() else 0)
    started = time.monotonic()
    with tarfile.open(src, "r:bz2") as tf:
        members = tf.getmembers()
        print("MEMBERS:", [(m.name, m.size) for m in members])
        for member in members:
            t0 = time.monotonic()
            tf.extract(member, path=str(dst))
            print(f"EXTRACTED {member.name} ({member.size} B) in {time.monotonic()-t0:.1f}s")
    print(f"ALL_DONE in {time.monotonic()-started:.1f}s")
