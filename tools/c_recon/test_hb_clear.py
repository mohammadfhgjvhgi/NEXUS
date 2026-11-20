from pathlib import Path
base = Path(r"M:\NEXUS\tools\c_relief\results")
for n in ("arduino15.phases.log", "arduino15.json"):
    (base / n).unlink(missing_ok=True)
(base / "hb_clear.txt").write_text("cleared", encoding="utf-8")
assert (base / "hb_clear.txt").exists()
