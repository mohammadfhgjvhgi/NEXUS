#!/usr/bin/env python3
"""Phase-10 live browser proof — runs on a REAL Chromium (CI + device).

One end-to-end §11.1 roundtrip, everything through the §8.2 router:

* launch the **agent session** (persistent context, isolated profile,
  headless flag from the environment);
* ``navigate`` a local ``file://`` page (no network dependency);
* ``read`` the DOM (§11.1 DOM);
* ``click`` + ``fill`` a form and read it back (§11.1 forms);
* ``upload`` a real file into the form's file input (§11.1 upload);
* ``download`` the same page to disk via the context request
  (§11.1 download);
* ``tabs`` · ``tab_new`` · ``tab_select`` · ``tab_close`` (§11.1 tabs);
* ``snapshot`` + ``screenshot`` (§11.1 browser states);
* close — the §11.4 session registry drains.

Run:  python tests/phase10/live_browser_ci.py
Exit 0 only when the whole chain passes.
"""

from __future__ import annotations

import http.server
import json
import socket
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.browser import set_engine_defaults  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402

PAGE = """<!doctype html>
<html><head><title>NEXUS Phase 10 Proof</title></head>
<body>
  <h1 id="title">Hello from NEXUS</h1>
  <form id="f">
    <input id="name" type="text" placeholder="name">
    <input id="file" type="file">
    <button id="go" type="button"
      onclick="document.getElementById('out').textContent =
               'submitted: ' + document.getElementById('name').value">
      Go
    </button>
  </form>
  <p id="out"></p>
</body></html>
"""


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexus-p10-live-"))
    page_path = workdir / "page.html"
    page_path.write_text(PAGE, encoding="utf-8")
    upload_path = workdir / "upload.txt"
    upload_path.write_text("phase-10 upload payload", encoding="utf-8")

    set_engine_defaults(
        channel="chromium", headless=True, data_root=workdir / "data"
    )
    _registry, router, _adapter, _report = build_tool_system(
        native=True, computer=False, browser=True, mcp_servers=()
    )

    def call(op: str, **arguments: object):
        outcome = router.route("browser", {"op": op, **arguments})
        print(f"  {op:<10} ok={outcome.ok} {str(outcome.output)[:80]}")
        return outcome

    checks: list[tuple[str, bool]] = []
    url = page_path.as_uri()
    outcome = call("navigate", url=url)
    checks.append(("navigate", outcome.ok and "NEXUS Phase 10 Proof" in outcome.output))

    outcome = call("read", selector="css=h1")
    checks.append((
        "dom read",
        outcome.ok and "Hello from NEXUS" in str(outcome.artifacts.get("text", "")),
    ))

    outcome = call("fill", selector="css=#name", text="agent-42")
    checks.append(("form fill", outcome.ok))
    outcome = call("click", selector="css=#go")
    checks.append(("form click", outcome.ok))
    outcome = call("read", selector="css=#out")
    checks.append((
        "form effect",
        outcome.ok and "agent-42" in str(outcome.artifacts.get("text", "")),
    ))

    outcome = call(
        "upload", selector="css=#file", path=str(upload_path)
    )
    checks.append(("upload", outcome.ok))

    outcome = call(
        "download", url=url, path=str(workdir / "downloaded.html")
    )
    checks.append((
        "download (file://)",
        outcome.ok and (workdir / "downloaded.html").stat().st_size > 0,
    ))

    # a real network download — a local http server through the
    # context request API (the §11.1 download path as deployed)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: ARG005
            *args, directory=str(workdir), **kwargs
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        outcome = call(
            "download",
            url=f"http://127.0.0.1:{port}/page.html",
            path=str(workdir / "downloaded_http.html"),
        )
        checks.append((
            "download (http)",
            outcome.ok and (workdir / "downloaded_http.html").stat().st_size > 0,
        ))
    finally:
        server.shutdown()

    outcome = call("tabs")
    checks.append(("tabs", outcome.ok))
    outcome = call("tab_new", url=url)
    checks.append(("tab_new", outcome.ok))
    outcome = call("tab_select", index=0)
    checks.append(("tab_select", outcome.ok))
    outcome = call("tab_close", index=1)
    checks.append(("tab_close", outcome.ok))

    outcome = call("snapshot")
    checks.append(("states snapshot", outcome.ok))
    outcome = call("screenshot", path=str(workdir / "proof.png"))
    checks.append((
        "screenshot",
        outcome.ok and (workdir / "proof.png").stat().st_size > 0,
    ))

    outcome = call("close")
    checks.append(("close", outcome.ok))

    failed = [label for label, ok in checks if not ok]
    print()
    print(json.dumps({
        "checks": len(checks),
        "failed": failed,
        "workdir": str(workdir),
    }, ensure_ascii=False))
    print("PROOF RESULT:", "PASS" if not failed else f"FAIL ({failed})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
