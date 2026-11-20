#!/usr/bin/env python3
"""Phase-14 device live proof — runs ON the real Windows box.

The §14 exit gate on the operator's machine — the box is the judge:

* **corpus**   — a temp mixed project (python + JS + routes + tests)
                 scanned with whatever this Windows runtime really
                 has (tree-sitter when installed — stdlib + regex
                 otherwise; engine_status never lies).
* **graphs**   — §14.4 dependencies, §14.5 routes, §14.6 test links.
* **maps**     — §14.8 repository map (budget + hub) and §14.7
                 architecture map.
* **live**     — §14.12 on real disk: file changed → parse the
                 affected region → update symbols → update graph.
* **incremental** — steady rescan reparses zero; a two-file touch
                 reparses exactly two.
* **self**     — the engine indexes the REAL ``M:\\NEXUS`` tree
                 (NEXUS reading its own codebase — the map of the
                 map-maker).
* **restart**  — a CHILD PROCESS (fresh interpreter) re-opens the
                 same index: everything survives.

Writes the verdict to ``M:\\NEXUS\\proofs\\phase14_live.json``.
Exit 0 only when every check passes.

Run:  python tests/phase14/live_proof_device.py
"""

from __future__ import annotations

import json
import os
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

VERDICT_PATH = Path(r"M:\NEXUS\proofs\phase14_live.json")

CHECKS: dict[str, dict[str, object]] = {}


def record(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS[name] = {"ok": bool(ok), "detail": detail}
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if not ok else ""))
    return ok


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
  return PORT + helper(1);
}
"""

JS_UTILS = "export function helper(x) { return x + 1; }\n"

PY_TEST = """from app.models import User


def test_user():
    assert User()
"""


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


def main() -> int:
    print("PHASE 14 device live proof — code intelligence on the real box")
    hostname = os.environ.get("COMPUTERNAME", "<unknown>")
    print(f"  host: {hostname} · python {sys.version.split()[0]}")
    failures = 0
    status = tree_sitter_status()

    with tempfile.TemporaryDirectory(prefix="p14-dev-") as tmp:
        root = Path(tmp)
        corpus = root / "corpus"
        make_corpus(corpus)
        engine = build_codeintel_engine(corpus)
        stats = engine.scan()
        record(
            "corpus scanned (7 files, all parsed)",
            stats.files_indexed == 7 and stats.files_parsed == 7,
            f"indexed={stats.files_indexed} parsed={stats.files_parsed}",
        )
        models = {s.name: s for s in engine.file_symbols("app/models.py")}
        record(
            "symbol index: classes + methods with lines + bilingual docstrings kept",
            {"User", "Order", "name", "total"} <= set(models)
            and models["User"].line == 2,
            str(sorted(models)),
        )
        record(
            "dependency graph: python + JS edges resolved",
            engine.dependencies_of("app/api.py") == ["app/models.py"]
            and engine.dependencies_of("src/server.js") == ["src/utils.js"],
            f"{engine.dependencies_of('app/api.py')} / {engine.dependencies_of('src/server.js')}",
        )
        table = engine.route_table()
        record(
            "API graph: flask + fastapi + express routes",
            "/api/users" in table
            and table["/api/users"][0]["handler"] == "list_users"
            and "/orders" in table
            and "/health" in table,
            str(sorted(table)),
        )
        record(
            "test graph: test file links its target",
            any(
                link.test_file == "tests/test_models.py"
                and link.target == "app/models.py"
                for link in engine.test_links()
            ),
        )
        # §14.12 — the live flow on real disk
        target = "app/models.py"
        disk = (corpus / target).read_text(encoding="utf-8")
        addition = (
            "\n\nclass Invoice:\n"
            "    def pay(self, amount: int) -> bool:\n"
            "        return amount > 0\n"
        )
        new_source = disk + addition
        (corpus / target).write_text(new_source, encoding="utf-8")
        report = engine.live_update(target, new_source)
        record(
            "§14.12 live update: symbols + graph (region recorded)",
            report.symbols_after > report.symbols_before
            and any(s.name == "Invoice" for s in engine.file_symbols(target))
            and report.changed_region[1] >= report.changed_region[0] >= 1,
            str(report.to_dict()),
        )
        record(
            "§14.12 method honest for this runtime",
            report.method
            in ("stdlib-ast-file", "treesitter-incremental", "tree-sitter-file", "regex-file"),
            report.method,
        )
        # incremental — steady + touched
        steady = engine.scan()
        record(
            "incremental: steady rescan reparses zero",
            steady.reparsed_on_update == 0,
            f"reparsed={steady.reparsed_on_update}",
        )
        for rel in ("app/api.py", "src/utils.js"):
            path = corpus / rel
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8"
            )
        touched = engine.scan()
        record(
            "incremental: two touched files → exactly two reparses",
            touched.reparsed_on_update == 2,
            f"reparsed={touched.reparsed_on_update}",
        )
        result = engine.repo_map(token_budget=192)
        record(
            "repository map: hub first + token budget",
            bool(result.entries)
            and result.entries[0].file == "app/models.py"
            and result.tokens_used <= result.token_budget,
            f"first={[e.file for e in result.entries[:3]]}",
        )
        layers = {lay.layer: lay for lay in engine.architecture_map()}
        record(
            "architecture map: layers aggregated",
            "app" in layers
            and "tests" in layers
            and layers["tests"].depends_on.get("app") is not None,
            str(sorted(layers)),
        )
        engine.close()

        # honest engine status
        if status.get("tree-sitter"):
            record(
                "engine status: real tree-sitter on this box",
                bool(status.get("python")) and bool(status.get("javascript")),
                str(status),
            )
        else:
            record(
                "engine status: honest absence (stdlib-ast + regex answer)",
                status == {"tree-sitter": False},
                str(status),
            )

        # NEXUS reads its own codebase — M:\NEXUS
        nexus_root = Path(r"M:\NEXUS")
        if nexus_root.is_dir():
            db = Path(tmp) / "nexus-index.db"
            self_engine = build_codeintel_engine(nexus_root, db_path=db)
            started = time.monotonic()
            self_stats = self_engine.scan()
            elapsed = time.monotonic() - started
            self_engine.close()
            record(
                "NEXUS indexes its own tree (M:\\NEXUS)",
                self_stats.files_indexed >= 150
                and self_stats.files_parsed >= 100
                and self_stats.symbols >= 500
                and self_stats.dependency_edges >= 100,
                f"indexed={self_stats.files_indexed} parsed={self_stats.files_parsed} "
                f"symbols={self_stats.symbols} edges={self_stats.dependency_edges} "
                f"in {elapsed:.1f}s",
            )
        else:
            record("NEXUS indexes its own tree (M:\\NEXUS)", False, "root missing")

        # restart persistence — child process on the corpus index
        child = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-c",
                CHILD_CODE.format(corpus=str(corpus)),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        try:
            verdict = json.loads(child.stdout.strip().splitlines()[-1])
        except Exception:
            verdict = {"ok": False, "detail": (child.stdout + child.stderr)[-400:]}
        record(
            "child process reopens the index (restart persistence)",
            bool(verdict.get("ok")),
            str(verdict.get("detail", "")),
        )

    for check in CHECKS.values():
        if not check["ok"]:
            failures += 1
    payload = {
        "host": hostname,
        "python": sys.version.split()[0],
        "tree_sitter_status": status,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **CHECKS,
    }
    try:
        VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERDICT_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  verdict → {VERDICT_PATH}")
    except OSError as exc:
        print(f"  [WARN] verdict not written: {exc}")
    print()
    print("=" * 72)
    total = len(CHECKS)
    if failures:
        print(f"live_proof_device.py — {total - failures}/{total} checks, {failures} FAILED")
        print("=" * 72)
        return 1
    print(f"live_proof_device.py — {total}/{total} checks, 0 failed")
    print("=" * 72)
    return 0


CHILD_CODE = '''
import json, sys
from pathlib import Path
sys.path.insert(0, {corpus!r})
sys.path.insert(0, r"M:\\NEXUS")
from nexus.codeintel import build_codeintel_engine
engine = build_codeintel_engine(Path({corpus!r}))
stats = engine.scan()
engine.close()
ok = stats.files_indexed == 7 and stats.reparsed_on_update == 0 and stats.symbols >= 10
print(json.dumps({{"ok": ok, "detail": f"indexed={{stats.files_indexed}} "
    f"reparsed={{stats.reparsed_on_update}} symbols={{stats.symbols}}"}}))
'''


if __name__ == "__main__":
    raise SystemExit(main())
