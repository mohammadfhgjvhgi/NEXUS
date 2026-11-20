from pathlib import Path
base = Path(r"M:\NEXUS\tools\c_relief\results")
(base / "mimo-snapshots.json").unlink(missing_ok=True)
(base / "v5_clear.txt").write_text("cleared", encoding="utf-8")
assert (base / "v5_clear.txt").exists()
