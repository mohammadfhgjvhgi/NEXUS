"""Native tool: ``filesystem`` (Final Build Plan §8.3).

Ten operations over :mod:`pathlib` — read_text · write_text ·
append_text · list_dir · make_dirs · move · copy · delete · stat ·
find. No shells, no string commands: every operation is a typed
library call, so the attack surface is the path itself (checked by
the §8.2 Scope stage) — not a command parser.

Relative paths resolve against the workspace root (injected at
registration); absolute paths pass through to the Scope stage. Reads
are bounded (2 MiB) with an honest truncation note. Writes/creates
report the resolved ``path`` artifact so the Verify stage proves the
effect on disk.

أداة نظام الملفات — عشر عمليات مكتبية آمنة، والقراءة
محدودة، والكتابة تُثبت أثرها على القرص.

Stdlib only.
"""

from __future__ import annotations

import shutil as _shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..models import (
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..models import (
    VerificationStrategy as V,
)
from .base import (
    NativeTool,
    object_schema,
    optional_str,
    output_schema,
    require_operation,
    require_str,
)

#: Bound on a single read (2 MiB) — honest truncation beyond it.
MAX_READ_BYTES = 2 * 1024 * 1024

_OPERATIONS: tuple[str, ...] = (
    "read_text",
    "write_text",
    "append_text",
    "list_dir",
    "make_dirs",
    "move",
    "copy",
    "delete",
    "stat",
    "find",
)
_MUTATING: tuple[str, ...] = (
    "write_text",
    "append_text",
    "make_dirs",
    "move",
    "copy",
    "delete",
)

_VERIFICATION_BY_OP: dict[str, VerificationSpec] = {
    "write_text": VerificationSpec(V.PATH_SIZE),
    "append_text": VerificationSpec(V.PATH_SIZE),
    "make_dirs": VerificationSpec(V.PATH_EXISTS),
    "move": VerificationSpec(V.PATH_EXISTS),
    "copy": VerificationSpec(V.PATH_EXISTS),
    "stat": VerificationSpec(V.JSON_FIELD, "stat"),
}


class FilesystemTool(NativeTool):
    """§8.3 ``filesystem`` — the unified file capability."""

    name = "filesystem"

    def __init__(self, *, workspace_root: Path | None = None) -> None:
        self._root = workspace_root

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:filesystem",
            name=self.name,
            description=(
                "Unified filesystem capability: read_text, write_text, "
                "append_text, list_dir, make_dirs, move, copy, delete, "
                "stat, find. Relative paths resolve to the workspace root."
            ),
            input_schema=object_schema(
                {
                    "op": {
                        "type": "string",
                        "enum": list(_OPERATIONS),
                        "description": "the filesystem operation",
                    },
                    "path": {
                        "type": "string",
                        "description": "target path (relative → workspace root)",
                    },
                    "to": {
                        "type": "string",
                        "description": "destination path for move/copy",
                    },
                    "content": {"type": "string", "description": "text to write"},
                    "pattern": {"type": "string", "description": "glob for find"},
                    "max_results": {
                        "type": "integer",
                        "description": "bound for find/list results (default 200)",
                    },
                },
                required=("op", "path"),
            ),
            output_schema=output_schema(
                "operation result: {op, path, detail…} + artifacts for Verify"
            ),
            permissions=("filesystem.read", "filesystem.write"),
            scope_requirements=ScopeRequirements(
                path_arguments=("path", "to"),
                mutating_operations=_MUTATING,
                dimensions=("filesystem",),
            ),
            risk=2,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    # ------------------------------------------------------------- plumbing

    def verification_for(self, operation: str) -> VerificationSpec:
        return _VERIFICATION_BY_OP.get(operation, VerificationSpec(V.NONE))

    def _resolve(self, raw: str) -> Path:
        candidate = Path(raw)
        if not candidate.is_absolute() and self._root is not None:
            candidate = self._root / candidate
        return candidate

    # -------------------------------------------------------------- handler

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        path = self._resolve(require_str(arguments, "path"))
        artifacts: dict[str, Any] = {"op": operation, "path": str(path)}

        if operation == "read_text":
            data = path.read_bytes()[: MAX_READ_BYTES + 1]
            truncated = len(data) > MAX_READ_BYTES
            text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
            if truncated:
                text += "\n[truncated at 2 MiB]"
            return ToolCallResult(output=text, artifacts=artifacts)

        if operation == "write_text":
            content = require_str(arguments, "content")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolCallResult(
                output=f"wrote {len(content)} chars to {path}", artifacts=artifacts
            )

        if operation == "append_text":
            content = require_str(arguments, "content")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(content)
            return ToolCallResult(
                output=f"appended {len(content)} chars to {path}", artifacts=artifacts
            )

        if operation == "list_dir":
            max_results = _bound(arguments.get("max_results"), default=200)
            entries = sorted(
                f"{'d' if entry.is_dir() else 'f'} {entry.name}"
                for entry in path.iterdir()
            )[:max_results]
            return ToolCallResult(
                output="\n".join(entries) if entries else "(empty directory)",
                artifacts={**artifacts, "entries": len(entries)},
            )

        if operation == "make_dirs":
            path.mkdir(parents=True, exist_ok=True)
            return ToolCallResult(output=f"directory ready: {path}", artifacts=artifacts)

        if operation == "move":
            destination = self._resolve(require_str(arguments, "to"))
            _shutil.move(str(path), str(destination))
            artifacts["path"] = str(destination)
            return ToolCallResult(
                output=f"moved to {destination}", artifacts=artifacts
            )

        if operation == "copy":
            destination = self._resolve(require_str(arguments, "to"))
            if path.is_dir():
                _shutil.copytree(str(path), str(destination))
            else:
                _shutil.copy2(str(path), str(destination))
            artifacts["path"] = str(destination)
            return ToolCallResult(
                output=f"copied to {destination}", artifacts=artifacts
            )

        if operation == "delete":
            if path.is_dir():
                _shutil.rmtree(str(path))
            else:
                path.unlink(missing_ok=True)
            return ToolCallResult(
                output=f"deleted {path}", artifacts={**artifacts, "path": ""}
            )

        if operation == "stat":
            info = path.stat()
            record = {
                "size": info.st_size,
                "modified": int(info.st_mtime),
                "is_dir": path.is_dir(),
            }
            return ToolCallResult(
                output=f"{path}: {record}", artifacts={**artifacts, "stat": record}
            )

        # find
        pattern = optional_str(arguments, "pattern") or "*"
        max_results = _bound(arguments.get("max_results"), default=200)
        matches = [str(item) for item in path.glob(pattern)][:max_results]
        return ToolCallResult(
            output="\n".join(matches) if matches else "(no matches)",
            artifacts={**artifacts, "matches": len(matches)},
        )

    def capabilities(self) -> Any:
        from ..models import CapabilityReport

        return CapabilityReport(
            available=True,
            reason="pathlib is always available",
            detail={"workspace_root": str(self._root) if self._root else None},
        )


def _bound(value: Any, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return min(value, 10_000)
