from pathlib import Path
base = Path(r"M:\NEXUS\tools\c_relief\results")
for n in ("mimo-snapshots.phases.log", "mimo-snapshots.json"):
    (base / n).unlink(missing_ok=True)
(base / "whale_clear.txt").write_text("cleared", encoding="utf-8")
assert (base / "whale_clear.txt").exists()
