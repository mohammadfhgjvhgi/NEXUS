"""Trivy integration (New Plan §21.9 — aquasecurity/trivy).

The plan, verbatim::

    Repository: aquasecurity/trivy
    استخدم في: dependency scanning · secret scanning · license
    scanning · vulnerability scanning

Two honest modes — the house pattern (§11.1 MODE A/B, §19.2, §14.9):

* **MODE A** — a real trivy binary on this host: ``trivy fs --format
  json --scanners …`` per kind, parsed into :class:`Finding` rows.
  The vulnerability scans download trivy's own database on first run
  (that database is the scanner's judgement — NEXUS adds none).
* **MODE B** — a stdlib :class:`BaselineScanner` when trivy is
  absent: dependency *inventory* from real manifests (requirements.txt
  · pyproject.toml · package.json), secret *detection* through the
  §21.7 redactor, license *declaration* detection (LICENSE files,
  SPDX headers, manifest fields) — and a vulnerability scan that
  reports its honesty in ``notes``: the baseline cannot judge
  vulnerabilities, because that needs trivy's database.  A missing
  engine is never a fake PASS.

One §21.10 law runs through both modes: a secret finding's snippet is
redacted before it becomes a report line — the scanner never
re-prints the secret it found.

الماسح على نمطين صادقين: trivy الحقيقي عند وجوده، وقاعدة أساسية
مكتبية عند غيابه — وفحص الثغرات لا يُختلق أبداً بلا قاعدة البيانات.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import (
    SCAN_KINDS,
    TRIVY_REPOSITORY,
    SecurityError,
    TrivyUnavailable,
    utc_now_iso,
)
from .redaction import Redactor

#: Directories the baseline walk never enters.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git", "node_modules", ".venv", "venv", "__pycache__",
        "dist", "build", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    }
)

#: Baseline walk budgets (bounded, always).
MAX_FILES = 2000
MAX_FILE_BYTES = 2_000_000

#: trivy's binary names across platforms.
TRIVY_BINARIES: tuple[str, ...] = ("trivy", "trivy.exe")


@dataclass(frozen=True, slots=True)
class Finding:
    """One scan finding — location + rule + severity, secret-free."""

    kind: str
    rule_id: str
    severity: str
    location: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "location": self.location,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ScanReport:
    """One scan's outcome — kind, mode, findings, honest notes."""

    kind: str
    target: str
    mode: str  # "trivy" | "baseline"
    findings: tuple[Finding, ...] = ()
    notes: tuple[str, ...] = ()
    timestamp: str = field(default_factory=utc_now_iso)
    scanner_version: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SCAN_KINDS:
            raise SecurityError(f"scan kind {self.kind!r} is not one of {SCAN_KINDS}")

    @property
    def count(self) -> int:
        return len(self.findings)

    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "mode": self.mode,
            "findings": [f.as_dict() for f in self.findings],
            "severity_counts": self.severity_counts(),
            "notes": list(self.notes),
            "timestamp": self.timestamp,
            "scanner_version": self.scanner_version,
        }


# ------------------------------------------------------------- MODE A


def _find_trivy() -> str | None:
    """The trivy binary, if this host has one.

    ``NEXUS_TRIVY_BINARY`` (a documented env seam) wins when it points
    at a real file — the device proof stages trivy on the box this way.
    """
    staged = os.environ.get("NEXUS_TRIVY_BINARY", "")
    if staged and Path(staged).is_file():
        return staged
    for name in TRIVY_BINARIES:
        found = shutil.which(name)
        if found:
            return found
    return None


class TrivyScanner:
    """MODE A — the real aquasecurity/trivy scanner."""

    repository = "aquasecurity/trivy"

    def __init__(
        self,
        binary: str | None = None,
        *,
        redactor: Redactor | None = None,
        timeout_vuln: int = 420,
        timeout_fast: int = 120,
    ) -> None:
        self._binary = binary
        self._redactor = redactor or Redactor()
        self._timeout_vuln = timeout_vuln
        self._timeout_fast = timeout_fast
        self._version: str | None = None

    # ------------------------------------------------------------ probes

    def available(self) -> bool:
        """True when trivy runs on this host (probed, never assumed)."""
        try:
            return bool(self.version())
        except (SecurityError, OSError):
            return False

    def version(self) -> str:
        """trivy's own version string (e.g. ``Version: 0.58.2``)."""
        if self._version is not None:
            return self._version
        binary = self._binary or _find_trivy()
        if not binary:
            raise TrivyUnavailable(
                f"trivy ({self.repository}) is not on this host — MODE B is honest"
            )
        try:
            proc = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TrivyUnavailable(f"trivy probe failed: {exc}") from exc
        if proc.returncode != 0:
            raise TrivyUnavailable(f"trivy --version failed: {proc.stderr[:200]}")
        self._version = proc.stdout.strip().splitlines()[0].strip()
        return self._version

    # ------------------------------------------------------------- scans

    def scan(self, target: Path | str, kind: str) -> ScanReport:
        """One real trivy scan of *kind* over *target*."""
        if kind not in SCAN_KINDS:
            raise SecurityError(f"scan kind {kind!r} is not one of {SCAN_KINDS}")
        binary = self._binary or _find_trivy()
        if not binary:
            raise TrivyUnavailable("trivy is not on this host")
        path = Path(target)
        if not path.exists():
            raise SecurityError(f"scan target {path} does not exist")
        scanners = "vuln" if kind in {"vulnerability", "dependency"} else kind
        is_pkg_scan = kind in {"vulnerability", "dependency"}
        timeout = self._timeout_vuln if is_pkg_scan else self._timeout_fast
        command = [
            binary, "fs", "--format", "json", "--scanners", scanners,
            "--quiet", str(path),
        ]
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except FileNotFoundError as exc:
            raise TrivyUnavailable(f"trivy binary is gone: {exc}") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise SecurityError(f"trivy scan failed: {exc}") from exc
        if proc.returncode != 0:
            raise SecurityError(
                f"trivy scan exited {proc.returncode}: {proc.stderr[-300:]}"
            )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SecurityError(f"trivy output is not JSON: {exc}") from exc
        findings = self._parse(payload, kind)
        return ScanReport(
            kind=kind,
            target=str(path),
            mode="trivy",
            findings=findings,
            scanner_version=self._clean(self.version()),
        )

    def scan_all(self, target: Path | str) -> dict[str, ScanReport]:
        """All four §21.9 kinds over *target*."""
        return {kind: self.scan(target, kind) for kind in SCAN_KINDS}

    # ------------------------------------------------------------ parsing

    def _parse(self, payload: dict[str, Any], kind: str) -> tuple[Finding, ...]:
        """trivy's JSON → findings (every free text redacted)."""
        results = payload.get("Results") or []
        findings: list[Finding] = []
        for result in results:
            file_target = self._clean(str(result.get("Target", "")))
            if kind in {"vulnerability", "dependency"}:
                if kind == "vulnerability":
                    for vuln in result.get("Vulnerabilities") or []:
                        findings.append(
                            Finding(
                                kind=kind,
                                rule_id=self._clean(str(vuln.get("VulnerabilityID", "CVE"))),
                                severity=str(vuln.get("Severity", "UNKNOWN")).upper(),
                                location=(
                                    f"{vuln.get('PkgName', '?')}"
                                    f"@{vuln.get('PkgPath') or file_target}"
                                ),
                                description=self._clean(
                                    str(vuln.get("Title") or vuln.get("Description", ""))[:220]
                                ),
                            )
                        )
                else:
                    for package in result.get("Packages") or []:
                        name = str(package.get("Name", "?"))
                        version = str(package.get("Version", "?"))
                        findings.append(
                            Finding(
                                kind=kind,
                                rule_id=self._clean(name),
                                severity="INFO",
                                location=f"{name}@{version} · {file_target}",
                                description=f"dependency {name} {version}",
                            )
                        )
            elif kind == "secret":
                for secret in result.get("Secrets") or []:
                    findings.append(
                        Finding(
                            kind=kind,
                            rule_id=self._clean(str(secret.get("RuleID", "secret"))),
                            severity=str(secret.get("Severity", "UNKNOWN")).upper(),
                            location=(
                                f"{result.get('Target', '?')}"
                                f":{secret.get('StartLine', '?')}"
                            ),
                            # §21.10: the match itself is never re-printed.
                            description=self._clean(
                                str(secret.get("Title") or secret.get("Match", ""))
                            ),
                        )
                    )
            elif kind == "license":
                for license_ in result.get("Licenses") or []:
                    findings.append(
                        Finding(
                            kind=kind,
                            rule_id=self._clean(
                                str(license_.get("Name") or license_.get("PkgName", "license"))
                            ),
                            severity=str(license_.get("Severity", "UNKNOWN")).upper(),
                            location=str(license_.get("FilePath") or file_target),
                            description=self._clean(
                                str(license_.get("Category", "license"))
                            ),
                        )
                    )
        return tuple(findings)

    def _clean(self, text: str) -> str:
        return self._redactor.redact_to_safe(text)


# ------------------------------------------------------------- MODE B


class BaselineScanner:
    """MODE B — the honest stdlib scanner (no trivy on this host)."""

    mode = "baseline"

    def __init__(self, redactor: Redactor | None = None) -> None:
        self._redactor = redactor or Redactor()

    # ------------------------------------------------------------- scans

    def scan(self, target: Path | str, kind: str) -> ScanReport:
        """One baseline scan of *kind* over *target*."""
        if kind not in SCAN_KINDS:
            raise SecurityError(f"scan kind {kind!r} is not one of {SCAN_KINDS}")
        path = Path(target)
        if not path.exists():
            raise SecurityError(f"scan target {path} does not exist")
        handler = {
            "dependency": self._scan_dependency,
            "secret": self._scan_secret,
            "license": self._scan_license,
            "vulnerability": self._scan_vulnerability,
        }[kind]
        return handler(path)

    def scan_all(self, target: Path | str) -> dict[str, ScanReport]:
        """All four §21.9 kinds over *target* (vulnerability honest)."""
        return {kind: self.scan(target, kind) for kind in SCAN_KINDS}

    # ------------------------------------------------------------ handlers

    def _scan_dependency(self, root: Path) -> ScanReport:
        """Real manifest inventory: requirements.txt · pyproject.toml ·
        package.json — versions as declared, no invented entries."""
        findings: list[Finding] = []
        for req in root.rglob("requirements*.txt"):
            if not self._walkable(req):
                continue
            for lineno, raw in enumerate(
                req.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                line = raw.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                match = re.match(
                    r"^([A-Za-z0-9_.\-]+)\s*(==|>=|~=|!=|<|>|===)?\s*([\w.\-]+)?", line
                )
                if not match:
                    continue
                name, op, version = match.group(1), match.group(2) or "", match.group(3) or ""
                findings.append(
                    Finding(
                        kind="dependency",
                        rule_id=name,
                        severity="INFO",
                        location=f"{req.name}:{lineno}",
                        description=f"{name} {op}{version}".strip(),
                    )
                )
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            findings.extend(self._pyproject_dependencies(pyproject))
        package_json = root / "package.json"
        if package_json.is_file():
            findings.extend(self._package_json_dependencies(package_json))
        return ScanReport(kind="dependency", target=str(root), mode=self.mode,
                          findings=tuple(findings))

    def _scan_secret(self, root: Path) -> ScanReport:
        """Pattern-based secret detection through the §21.7 redactor —
        and every finding's snippet is redacted before it is stored."""
        findings: list[Finding] = []
        seen = 0
        for file_path in self._iter_files(root):
            seen += 1
            if seen > MAX_FILES:
                break
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for finding in self._redactor.findings(line):
                    findings.append(
                        Finding(
                            kind="secret",
                            rule_id=finding.kind,
                            severity="HIGH",
                            location=f"{file_path.relative_to(root)}:{lineno}",
                            # the span itself stays redacted — §21.10
                            description=self._redactor.redact_to_safe(
                                line.strip()[:120]
                            ),
                        )
                    )
        return ScanReport(kind="secret", target=str(root), mode=self.mode,
                          findings=tuple(findings))

    def _scan_license(self, root: Path) -> ScanReport:
        """License declarations: LICENSE/COPYING files · SPDX headers ·
        manifest license fields."""
        findings: list[Finding] = []
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "COPYING.txt"):
            license_file = root / name
            if license_file.is_file():
                first_line = license_file.read_text(
                    encoding="utf-8", errors="replace"
                ).strip().splitlines()
                headline = first_line[0].strip() if first_line else name
                findings.append(
                    Finding(
                        kind="license",
                        rule_id="license-file",
                        severity="INFO",
                        location=name,
                        description=self._redactor.redact_to_safe(headline[:120]),
                    )
                )
        for file_path in self._iter_files(root):
            if file_path.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".toml"}:
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")[:20000]
            except OSError:
                continue
            for match in re.finditer(r"SPDX-License-Identifier:\s*([\w.\-]+)", text):
                findings.append(
                    Finding(
                        kind="license",
                        rule_id=match.group(1),
                        severity="INFO",
                        location=str(file_path.relative_to(root)),
                        description="SPDX header",
                    )
                )
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'(?m)^license\s*=\s*[{\["\']?\s*("?)([\w.\-+() ]+)\1', text)
            if match:
                findings.append(
                    Finding(
                        kind="license",
                        rule_id=match.group(2).strip(),
                        severity="INFO",
                        location="pyproject.toml",
                        description="declared license",
                    )
                )
        return ScanReport(kind="license", target=str(root), mode=self.mode,
                          findings=tuple(findings))

    def _scan_vulnerability(self, root: Path) -> ScanReport:
        """The honest refusal — a baseline cannot judge vulnerabilities.

        Zero findings here would be a fabricated PASS; the report
        carries the reason in ``notes`` and stays empty.
        """
        return ScanReport(
            kind="vulnerability",
            target=str(root),
            mode=self.mode,
            findings=(),
            notes=(
                "baseline mode cannot judge vulnerabilities — the "
                "aquasecurity/trivy database is required (MODE A)",
            ),
        )

    # ------------------------------------------------------------ helpers

    def _pyproject_dependencies(self, path: Path) -> list[Finding]:
        """tomllib (stdlib, py≥3.11) parse of [project] dependencies."""
        import tomllib

        findings: list[Finding] = []
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (tomllib.TOMLDecodeError, OSError):
            return findings
        for dep in (data.get("project") or {}).get("dependencies", []) or []:
            match = re.match(r"^([A-Za-z0-9_.\-]+)\s*([=<>!~]+)?\s*([\w.\-]+)?", str(dep))
            if not match:
                continue
            name, op, version = match.group(1), match.group(2) or "", match.group(3) or ""
            findings.append(
                Finding(
                    kind="dependency",
                    rule_id=name,
                    severity="INFO",
                    location=path.name,
                    description=f"{name} {op}{version}".strip(),
                )
            )
        return findings

    def _package_json_dependencies(self, path: Path) -> list[Finding]:
        findings: list[Finding] = []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return findings
        for section in ("dependencies", "devDependencies"):
            for name, version in (data.get(section) or {}).items():
                findings.append(
                    Finding(
                        kind="dependency",
                        rule_id=str(name),
                        severity="INFO",
                        location=f"{path.name}#{section}",
                        description=f"{name} {version}",
                    )
                )
        return findings

    def _iter_files(self, root: Path) -> list[Path]:
        """A bounded walk that never enters SKIP_DIRS."""
        files: list[Path] = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            files.append(file_path)
            if len(files) >= MAX_FILES:
                break
        return files

    @staticmethod
    def _walkable(path: Path) -> bool:
        return path.is_file() and not any(part in SKIP_DIRS for part in path.parts)


def make_scanner(
    *,
    redactor: Redactor | None = None,
    prefer_trivy: bool = True,
) -> TrivyScanner | BaselineScanner:
    """MODE A when trivy runs here, MODE B honestly when it does not."""
    scanner: TrivyScanner | BaselineScanner = BaselineScanner(redactor=redactor)
    if prefer_trivy:
        trivy = TrivyScanner(redactor=redactor)
        if trivy.available():
            return trivy
    return scanner


__all__ = [
    "BaselineScanner",
    "Finding",
    "MAX_FILE_BYTES",
    "MAX_FILES",
    "SCAN_KINDS",
    "SKIP_DIRS",
    "ScanReport",
    "SecurityError",
    "TRIVY_BINARIES",
    "TRIVY_REPOSITORY",
    "TrivyScanner",
    "TrivyUnavailable",
    "make_scanner",
]
