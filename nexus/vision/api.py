"""Vision API façade (Final Build Plan §12 — over the §8.2 router).

The §12.1 capture domains, the §12.2 provider verbs and the §12.5
OCR — every one a **thin router client** (``router.route`` through
the seven-stage pipeline), exactly like the §9.1 Computer API: the
façade is policy and orchestration, the router stays the single
gate every real-world effect passes through.

الواجهة — لقطة ورؤية وتعرّف خلف الموجّه نفسه، لا بوابة ثانية.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..tools.router import ToolRouter


class VisionApiError(Exception):
    """A vision domain call failed — honest, with the operation."""


#: The §12 domains this façade routes, verbatim.
VISION_DOMAINS: tuple[str, ...] = ("capture", "analyze", "locate",
                                   "classify", "compare", "ocr")

#: Domain → dispatch tool name (the §8.1 ``vision`` record).
_DOMAIN_TOOLS: dict[str, str] = {domain: "vision" for domain in VISION_DOMAINS}


class VisionRuntime:
    """The §12 façade — one route per vision operation."""

    def __init__(
        self,
        router: ToolRouter,
        *,
        policy: Any = None,
        workspace_id: str | None = None,
        agent_id: str = "vision",
    ) -> None:
        self._router = router
        self._policy = policy
        self._workspace_id = workspace_id
        self._agent_id = agent_id
        self._active_task_id = ""

    @property
    def router(self) -> ToolRouter:
        return self._router

    # ------------------------------------------------------------ verbs

    def capture(
        self,
        mode: str,
        *,
        path: str,
        hwnd: int | None = None,
        x: int = 0,
        y: int = 0,
        w: int = 0,
        h: int = 0,
        task_id: str = "",
    ) -> Any:
        """§12.1 ``full | window | region`` → a scope-checked PNG path."""
        arguments: dict[str, Any] = {"op": "capture", "mode": mode, "path": path}
        if hwnd is not None:
            arguments["hwnd"] = hwnd
        if mode == "region":
            arguments.update({"x": x, "y": y, "w": w, "h": h})
        return self._route("capture", arguments, task_id=task_id)

    def analyze(self, path: str, *, question: str, task_id: str = "") -> Any:
        """§12.2 ``analyze`` — one image, one question, one report."""
        return self._route(
            "analyze",
            {"op": "analyze", "path": path, "question": question},
            task_id=task_id,
        )

    def locate(
        self, path: str, *, description: str, task_id: str = ""
    ) -> Any:
        """§12.2 ``locate`` — one element description → pixels."""
        return self._route(
            "locate",
            {"op": "locate", "path": path, "description": description},
            task_id=task_id,
        )

    def classify(
        self, path: str, *, categories: list[str], task_id: str = ""
    ) -> Any:
        """§12.2 ``classify`` — one image into one of a given set."""
        return self._route(
            "classify",
            {"op": "classify", "path": path, "categories": categories},
            task_id=task_id,
        )

    def compare(
        self, path_a: str, path_b: str, *, task_id: str = ""
    ) -> Any:
        """§12.2 ``compare`` — two images, one verdict."""
        return self._route(
            "compare",
            {"op": "compare", "path": path_a, "path_b": path_b},
            task_id=task_id,
        )

    def ocr(self, path: str, *, task_id: str = "") -> Any:
        """§12.5 ``ocr`` — the benchmarked engine, one image."""
        return self._route(
            "ocr", {"op": "ocr", "path": path}, task_id=task_id
        )

    # ------------------------------------------------------------ engine

    def _route(
        self,
        domain: str,
        arguments: Mapping[str, Any],
        *,
        task_id: str = "",
    ) -> Any:
        if domain not in _DOMAIN_TOOLS:
            raise VisionApiError(f"unknown vision domain {domain!r}")
        outcome = self._router.route(
            _DOMAIN_TOOLS[domain],
            arguments,
            task_id=task_id or self._active_task_id,
            agent_id=self._agent_id,
            policy=self._policy,
            workspace_id=self._workspace_id,
        )
        return outcome

    def capability_report(self) -> dict[str, Any]:
        """Per-domain honest probe (registry probes, no guessing)."""
        report: dict[str, Any] = {}
        for domain in VISION_DOMAINS:
            registered = self._router.registry.get(_DOMAIN_TOOLS[domain])
            if registered is None:
                report[domain] = {
                    "available": False, "reason": "not registered",
                }
                continue
            capability = registered.capabilities()
            report[domain] = {
                "available": bool(capability.available),
                "reason": capability.reason,
            }
        return report


__all__ = ["VISION_DOMAINS", "VisionApiError", "VisionRuntime"]
