#!/usr/bin/env python3
"""Phase-14 live code-intelligence proof — real tree-sitter, real 100k.

One end-to-end §14 rung on whatever this runtime really has — no
fakes, no mocks:

* **engine**   — :func:`tree_sitter_status` reports the real grammars
                 (python + javascript must both be present for the
                 MODE A live path).
* **MODE A**   — JavaScript parsed by the real tree-sitter (a
                 language stdlib cannot touch), python through
                 tree-sitter too (``prefer="tree-sitter"``).
* **100k**     — §14.11's first rung for real: 100,000 generated
                 python files scanned (full file index, honest parse
                 budget, crawl continuation across restarts).
* **incremental** — a corpus root scanned twice: the second pass
                 reparses NOTHING (steady state), a 3-file touch
                 reparses exactly 3.
* **live**     — §14.12 on real files: python AND javascript edits
                 through the true incremental path
                 (``treesitter-incremental``), symbols + graph
                 updated, changed region recorded.
* **maps**     — the §14.8 repository map (token-budgeted, hub
                 ranked) and the §14.7 architecture map.
* **restart**  — a CHILD PROCESS (fresh interpreter) re-opens the
                 100k index: every file survives, the crawl continues
                 exactly where it stopped.

Fail-fast: anything missing → exit 1 with the honest reason.

Run:  python tests/phase14/live_codeintel_ci.py
Exit 0 only when the whole chain passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.codeintel import (  # noqa: E402
    build_codeintel_engine,
    tree_sitter_status,
)

# ------------------------------------------------------------------ corpus

PY_MODELS = '''# النماذج — طبقة البيانات
class User:
    """مستخدم النظام."""

    def name(self) -> str:
        return "مستخدم"


class Order:
    def total(self, items: int) -> int:
        return items
'''

PY_API = '''from app.models import User, Order


@app.route("/api/users", methods=["GET", "POST"])
def list_users():
    return [User()]


@router.post("/orders")
def create_order():
    return Order()
'''

PY_SERVICE = '''from app.models import User
from app.api import list_users

SERVICE_NAME = "nexus"


def run_service(user: User) -> str:
    return user.name()
'''

JS_SERVER = """import { helper } from './utils.js';
const PORT = 3000;

export function start(app) {
  app.get('/health', (req, res) => res.send('ok'));
  app.post('/items', (req, res) => res.json([]));
  return PORT + helper(1);
}
"""

JS_UTILS = "export function helper(x) { return x + 1; }\n"

PY_TEST = """from app.models import User


def test_user():
    assert User()
"""

FILE_CONTENT = "class C{idx}:\n    def m(self):\n        return {idx}\n"


def make_corpus(root: Path) -> None:
    (root / "app").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "models.py").write_text(PY_MODELS, encoding="utf-8")
    (root / "app" / "api.py").write_text(PY_API, encoding="utf-8")
    (root / "app" / "service.py").write_text(PY_SERVICE, encoding="utf-8")
    (root / "src" / "server.js").write_text(JS_SERVER, encoding="utf-8")
    (root / "src" / "utils.js").write_text(JS_UTILS, encoding="utf-8")
    (root / "tests" / "test_models.py").write_text(PY_TEST, encoding="utf-8")


def make_100k(root: Path) -> float:
    """100,000 tiny python files — §14.11's first rung, generated fast."""
    started = time.monotonic()
    for d in range(200):
        folder = root / f"m{d:04d}"
        folder.mkdir()
        for i in range(500):
            (folder / f"f{i:04d}.py").write_text(
                FILE_CONTENT.format(idx=i), encoding="utf-8"
            )
    return time.monotonic() - started


# ------------------------------------------------------------------- proof

CHECKS: dict[str, dict[str, object]] = {}


def record(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS[name] = {"ok": bool(ok), "detail": detail}
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    return ok


def main() -> int:
    print("PHASE 14 live proof — code intelligence (tree-sitter MODE A + 100k)")
    failures = 0

    # 1 — the real engines
    status = tree_sitter_status()
    ok = bool(status.get("tree-sitter")) and bool(status.get("python")) and bool(
        status.get("javascript")
    )
    record("tree-sitter present with python+javascript grammars", ok, str(status))
    if not ok:
        return _finish(1)

    with tempfile.TemporaryDirectory(prefix="p14-live-") as tmp:
        root = Path(tmp)

        # 2 — the corpus (mixed python + JS + routes + tests)
        corpus = root / "corpus"
        make_corpus(corpus)
        engine = build_codeintel_engine(corpus, prefer="tree-sitter")
        stats = engine.scan()
        record(
            "corpus scanned (7 files, all parsed)",
            stats.files_indexed == 7 and stats.files_parsed == 7,
            f"indexed={stats.files_indexed} parsed={stats.files_parsed}",
        )
        js_symbols = {s.name for s in engine.file_symbols("src/server.js")}
        record(
            "MODE A: JavaScript parsed by real tree-sitter",
            "start" in js_symbols and "PORT" in js_symbols,
            str(sorted(js_symbols)),
        )
        py_engine_used = engine.stats().last_engine
        record(
            "MODE A: python through tree-sitter too (prefer)",
            py_engine_used == "tree-sitter",
            py_engine_used,
        )
        record(
            "API graph live (flask + fastapi + express routes)",
            len(engine.api_endpoints()) == 4,
            str(len(engine.api_endpoints())),
        )
        record(
            "test graph live",
            any(
                link.test_file == "tests/test_models.py"
                and link.target == "app/models.py"
                for link in engine.test_links()
            ),
        )
        # 3 — incremental steady state + 3-file touch
        steady = engine.scan()
        record(
            "steady rescan reparses zero",
            steady.reparsed_on_update == 0,
            f"reparsed={steady.reparsed_on_update}",
        )
        for rel in ("app/api.py", "app/service.py", "src/utils.js"):
            path = corpus / rel
            path.write_text(path.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
        touched = engine.scan()
        record(
            "three touched files → exactly three reparses",
            touched.reparsed_on_update == 3,
            f"reparsed={touched.reparsed_on_update}",
        )

        # 4 — §14.12 live update — python (tree-sitter incremental)
        target = "app/models.py"
        disk = (corpus / target).read_text(encoding="utf-8")
        addition = (
            "\n\nclass Invoice:\n"
            "    def pay(self, amount: int) -> bool:\n"
            "        return amount > 0\n"
        )
        new_py = disk + addition
        (corpus / target).write_text(new_py, encoding="utf-8")
        report = engine.live_update(target, new_py)
        record(
            "§14.12 python: treesitter-incremental",
            report.method == "treesitter-incremental",
            report.method,
        )
        record(
            "§14.12 python: region + symbol growth",
            report.changed_region[1] > report.changed_region[0]
            and report.symbols_after > report.symbols_before
            and any(s.name == "Invoice" for s in engine.file_symbols(target)),
            str(report.to_dict()),
        )
        # 5 — §14.12 live update — javascript (tree-sitter incremental)
        js_target = "src/server.js"
        js_disk = (corpus / js_target).read_text(encoding="utf-8")
        js_addition = (
            "\nexport function shutdown(app) {\n"
            "  app.get('/shutdown', (req, res) => res.send('bye'));\n"
            "  return true;\n"
            "}\n"
        )
        new_js = js_disk + js_addition
        (corpus / js_target).write_text(new_js, encoding="utf-8")
        js_report = engine.live_update(js_target, new_js)
        record(
            "§14.12 javascript: treesitter-incremental",
            js_report.method == "treesitter-incremental",
            js_report.method,
        )
        record(
            "§14.12 javascript: express route materializes",
            any(ep.path == "/shutdown" for ep in engine.api_endpoints()),
        )
        # 6 — a live edit that adds a project import → edge materializes
        svc = "app/service.py"
        svc_disk = (corpus / svc).read_text(encoding="utf-8")
        new_svc = "from app.models import Order\n" + svc_disk
        (corpus / svc).write_text(new_svc, encoding="utf-8")
        svc_report = engine.live_update(svc, new_svc)
        record(
            "§14.12 update graph: edge materializes instantly",
            "app/models.py" in engine.dependencies_of(svc)
            and svc_report.edges_rebuilt >= 2,
            str(svc_report.to_dict()),
        )
        # 7 — the maps
        result = engine.repo_map(token_budget=192)
        record(
            "§14.8 repository map: hub ranked + budget",
            bool(result.entries)
            and result.entries[0].file == "app/models.py"
            and result.tokens_used <= result.token_budget,
            f"first={[e.file for e in result.entries[:3]]} tokens={result.tokens_used}",
        )
        layers = {lay.layer: lay for lay in engine.architecture_map()}
        record(
            "§14.7 architecture map: layers + aggregated deps",
            "tests" in layers
            and layers["tests"].depends_on.get("app") is not None,
            str(sorted(layers)),
        )
        impact = engine.impact("app/models.py")
        record(
            "§14.4 impact: change models breaks api + service + tests",
            {"app/api.py", "app/service.py", "tests/test_models.py"} <= set(impact),
            str(impact),
        )
        engine.close()

        # 8 — the 100k rung
        big = root / "big"
        big.mkdir()
        gen_seconds = make_100k(big)
        record("100,000 files generated", True, f"{gen_seconds:.1f}s")
        big_engine = build_codeintel_engine(big)
        started = time.monotonic()
        big_stats = big_engine.scan(parse_budget=2_500)
        scan_seconds = time.monotonic() - started
        record(
            "100k scanned: full file index + honest budget",
            big_stats.files_indexed == 100_000
            and big_stats.files_parsed == 2_500
            and big_stats.files_skipped == 97_500,
            f"indexed={big_stats.files_indexed} "
            f"parsed={big_stats.files_parsed} in {scan_seconds:.1f}s",
        )
        record("100k scan completes in CI time", scan_seconds < 180, f"{scan_seconds:.1f}s")
        second = big_engine.scan(parse_budget=2_500)
        record(
            "100k crawl continues (2,500 → 5,000, no restart)",
            second.files_parsed == 5_000 and second.reparsed_on_update == 2_500,
            f"parsed={second.files_parsed} reparsed={second.reparsed_on_update}",
        )
        big_engine.close()

        # 9 — restart persistence — a CHILD PROCESS re-opens the 100k index
        child = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-c",
                CHILD_CODE.format(root=str(big)),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        try:
            verdict = json.loads(child.stdout.strip().splitlines()[-1])
        except Exception:
            verdict = {"ok": False, "detail": child.stdout[-400:] + child.stderr[-400:]}
        record(
            "child process reopens the 100k index (restart persistence)",
            bool(verdict.get("ok")),
            str(verdict.get("detail", "")),
        )

    for check in CHECKS.values():
        if not check["ok"]:
            failures += 1
    return _finish(failures)


CHILD_CODE = '''
import json, sys
sys.path.insert(0, {root!r})
from pathlib import Path
from nexus.codeintel import build_codeintel_engine
engine = build_codeintel_engine(Path({root!r}))
stats = engine.scan(parse_budget=1_000)
engine.close()
ok = (
    stats.files_indexed == 100_000
    and stats.files_parsed == 6_000
    and stats.reparsed_on_update == 1_000
)
print(json.dumps({{"ok": ok, "detail": f"indexed={{stats.files_indexed}} "
    f"parsed={{stats.files_parsed}} reparsed={{stats.reparsed_on_update}}"}}))
'''


def _finish(failures: int) -> int:
    print()
    print("=" * 72)
    total = len(CHECKS)
    if failures:
        print(f"live_codeintel_ci.py — {total - failures}/{total} checks, {failures} FAILED")
        print("=" * 72)
        return 1
    print(f"live_codeintel_ci.py — {total}/{total} checks, 0 failed")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
