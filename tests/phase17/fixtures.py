"""Phase-17 test fixtures — real surfaces, all local, all honest.

Three HTTP servers on 127.0.0.1 (a generic web engine, a Discourse-style
forum, a GitHub-API stub), one documentation corpus, one local-files
tree, and a GitHub engine pointed at the stub.  No third-party imports.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

WEB_DOCS = [
    {"title": "llama.cpp README", "url": "https://github.com/ggml-org/llama.cpp",
     "snippet": "llama.cpp runs LLM inference locally with GGUF quantized models."},
    {"title": "llama.cpp README (mirror)", "url": "https://github.com/ggml-org/llama.cpp",
     "snippet": "llama.cpp runs LLM inference locally with GGUF quantized models."},
    {"title": "GGUF memory guide", "url": "https://docs.example.com/gguf-ram.html",
     "snippet": "A 7B Q4 GGUF model needs about 4 GB of free RAM to run."},
    {"title": "Someone's blog on quantization", "url": "https://alice.wordpress.com/quant",
     "snippet": "A 7B Q4 GGUF model needs roughly 4 GB of RAM on my laptop."},
    {"title": "arXiv: quantization survey", "url": "https://arxiv.org/abs/2401.99999",
     "snippet": "We survey 4-bit quantization for 7B parameter models."},
]

FORUM_TOPICS = [
    {"title": "llama.cpp 7B RAM question", "url": "https://forum.example.com/t/12",
     "blurb": "How much RAM does a 7B model take? about 4 GB in practice"},
    {"title": "GGUF thread", "url": "https://forum.example.com/t/99",
     "blurb": "gguf models run fine locally, 4 GB was enough here"},
]

GH_REPOS = {
    "items": [
        {"name": "llama.cpp", "owner": {"login": "ggml-org"},
         "html_url": "https://github.com/ggml-org/llama.cpp",
         "clone_url": "https://github.com/ggml-org/llama.cpp.git",
         "stargazers_count": 90000, "license": {"spdx_id": "MIT"},
         "pushed_at": "2026-01-10T00:00:00Z", "archived": False,
         "description": "LLM inference in C/C++", "language": "C++"},
    ],
}


class _SurfaceHandler(BaseHTTPRequestHandler):
    """One server, several personalities — by path prefix."""

    def log_message(self, *args: Any) -> None:
        return

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/web"):
            self._send(200, {"results": WEB_DOCS})
        elif self.path.startswith("/search.json"):
            self._send(200, {"topics": FORUM_TOPICS})
        elif self.path.startswith("/search/repositories"):
            self._send(200, GH_REPOS)
        elif self.path.startswith("/broken"):
            self._send(500, {"message": "kaboom"})
        else:
            self._send(404, {"message": "no such surface"})


class SurfaceServer:
    """The §17.1 HTTP surfaces + a broken one, on 127.0.0.1."""

    def __init__(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _SurfaceHandler)
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.port = self.httpd.server_address[1]

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> SurfaceServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()


def make_docs_corpus(root: Path) -> Path:
    """A real documentation corpus (md/txt) with overlapping facts."""
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "gguf-memory.md").write_text(
        "# GGUF memory\n\nA 7B Q4 GGUF model needs about 4 GB of RAM to run locally.\n"
        "llama.cpp loads GGUF models with mmap.\n",
        encoding="utf-8",
    )
    (docs / "llama-cpp.md").write_text(
        "# llama.cpp\n\nllama.cpp runs GGUF models locally on CPU and GPU.\n"
        "A 7B model at Q4 fits in 4 GB of RAM.\n",
        encoding="utf-8",
    )
    (docs / "unrelated.md").write_text(
        "# Unrelated\n\nThe keyboard layout can be changed per window.\n",
        encoding="utf-8",
    )
    return docs


def make_local_tree(root: Path) -> Path:
    """A real local-files tree (code + notes)."""
    tree = root / "workspace"
    (tree / "notes").mkdir(parents=True, exist_ok=True)
    (tree / "notes" / "todo.txt").write_text(
        "benchmark llama.cpp with the 7B GGUF model on the local GPU\n",
        encoding="utf-8",
    )
    (tree / "notes" / "shopping.txt").write_text("milk eggs bread\n", encoding="utf-8")
    (tree / "bench.py").write_text(
        "import time  # time llama.cpp inference locally\nprint('bench')\n",
        encoding="utf-8",
    )
    return tree
