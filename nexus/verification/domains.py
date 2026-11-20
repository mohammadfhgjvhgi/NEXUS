"""The nine verification domains (New Plan §20.2).

One :class:`~nexus.verification.contracts.Verifier` per domain, verbatim
from the plan and in its order::

    Software   Windows   Browser   Documents   Research
    Git   Memory   Models   System

Every verifier declares its criteria up front and judges them through
one honest engine (:class:`BaseVerifier.verify`):

* the check returns a string  → **PASS** with that observation,
* the check raises ``AssertionError`` → **FAIL** — the claim did not hold,
* the check raises :class:`~nexus.verification.contracts.CriterionSkipped`
  → **SKIP** — this host honestly cannot judge it (the Windows facts are
  judged on the real Windows box, not on a Linux CI runner),
* anything else raises → **ERROR** — the probe itself is broken, never
  disguised as a FAIL or a SKIP.

The probes are real: the memory domain runs an actual §12 engine
roundtrip (remember → retrieve → close — closed *before* the temp dir
is removed, the Windows handle lesson), the git domain reads the real
HEAD sha, the system domain writes a real temp file and measures real
disk.  No capability row is invented without proof.

التسع مجالات — مسبارات حقيقية، ونتائج صادقة: PASS ببرهان، وSKIP
لما لا يستطيع هذا المضيف الحكم عليه، ولا اختراع إطلاقاً.

Stdlib only.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

from .contracts import (
    REPAIR_STAGES,
    VERIFICATION_DOMAINS,
    Criterion,
    CriterionSkipped,
    Evidence,
    Result,
    ResultStatus,
    VerificationError,
    Verifier,
)
from .evidence import EvidenceStore

#: Output observations are kept at a readable size (the reports stay honest
#: and printable); the full observation still lands inside the evidence.
_MAX_OUTPUT = 400

#: The default Windows checkpoint (the M:\NEXUS law) — overridable.
DEFAULT_CHECKPOINT = r"M:\NEXUS"


# ------------------------------------------------------------ base engine


class BaseVerifier(Verifier):
    """The honest judging engine shared by the nine domains.

    Subclasses declare :meth:`~nexus.verification.contracts.Verifier.criteria`
    whose ``check`` callables do the real probing; this base runs each
    check, times it, and wraps the observation in §20.3 evidence (and,
    when a store is attached, persists it and records the artifact).
    """

    def __init__(self, store: EvidenceStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> EvidenceStore | None:
        return self._store

    # ------------------------------------------------------------------

    def verify(self, criterion: Criterion) -> Result:
        """One criterion → an honest Result with its evidence chain."""
        if criterion.check is None:
            raise VerificationError(
                f"criterion {criterion.id} declares no check — nothing to prove"
            )
        t0 = time.perf_counter()
        status: ResultStatus
        try:
            output = str(criterion.check())
        except CriterionSkipped as skipped:
            status, output, message = ResultStatus.SKIP, f"skipped: {skipped}", str(skipped)
        except AssertionError as exc:
            status, output, message = ResultStatus.FAIL, f"failed: {exc}", str(exc)
        except Exception as exc:  # noqa: BLE001 — the probe itself broke
            status = ResultStatus.ERROR
            output = f"error: {type(exc).__name__}: {exc}"
            message = f"{type(exc).__name__}: {exc}"
        else:
            status, message = ResultStatus.PASS, ""
        duration = time.perf_counter() - t0
        evidence = Evidence(
            method=f"check:{criterion.id}",
            output=output[:_MAX_OUTPUT],
            result=status,
        )
        if self._store is not None:
            evidence = self._store.record(evidence)
        return Result(
            criterion_id=criterion.id,
            status=status,
            evidence=(evidence,),
            duration_seconds=duration,
            message=message,
        )


# ----------------------------------------------------------- §20.2 software


class SoftwareVerifier(BaseVerifier):
    """The *Software* domain — the shipped code itself is the first claim."""

    id = "software-verifier"
    domain = "software"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_imports() -> str:
            import importlib

            modules = [
                "nexus",
                "nexus.core.engine",
                "nexus.core.session",
                "nexus.core.persistence",
                "nexus.events",
                "nexus.memory",
                "nexus.research",
                "nexus.documents",
                "nexus.speech",
                "nexus.verification",
            ]
            for name in modules:
                importlib.import_module(name)
            return f"imported {len(modules)} core modules: {', '.join(modules[-4:])}…"

        def version_integrity() -> str:
            import nexus

            parts = nexus.__version__.split(".")
            assert len(parts) == 3, f"version {nexus.__version__!r} is not major.minor.patch"
            major, minor, patch = (int(p) for p in parts)
            assert (major, minor, patch) >= (0, 20, 0), (
                f"version below the phase floor: {nexus.__version__}"
            )
            assert isinstance(nexus.NEXUS_PHASE, int) and nexus.NEXUS_PHASE >= 20
            return f"nexus {nexus.__version__} · NEXUS_PHASE={nexus.NEXUS_PHASE}"

        def plan_vocabularies() -> str:
            assert VERIFICATION_DOMAINS == (
                "software", "windows", "browser", "documents", "research",
                "git", "memory", "models", "system",
            ), "the nine §20.2 domains must stay verbatim and ordered"
            assert REPAIR_STAGES == ("fail", "diagnose", "fix", "retest", "verify"), (
                "the five §20.4 stages must stay verbatim and ordered"
            )
            return (
                f"{len(VERIFICATION_DOMAINS)} domains · "
                f"{len(REPAIR_STAGES)} repair stages, verbatim"
            )

        def pyproject_integrity() -> str:
            import tomllib

            import nexus

            root = Path(nexus.__file__).resolve().parent.parent
            data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
            version = data["project"]["version"]
            assert version == nexus.__version__, (
                f"pyproject {version} != package {nexus.__version__}"
            )
            assert data["project"]["dependencies"] == [], "the core must stay stdlib-only"
            return f"pyproject {version} == package · dependencies stdlib-only"

        return (
            Criterion(
                id="software-package-imports",
                domain=self.domain,
                description="the NEXUS core and the phase packages import cleanly",
                check=package_imports,
            ),
            Criterion(
                id="software-version-integrity",
                domain=self.domain,
                description=(
                    "__version__ is a real semver at the phase floor "
                    "and NEXUS_PHASE matches"
                ),
                check=version_integrity,
            ),
            Criterion(
                id="software-plan-vocabularies",
                domain=self.domain,
                description="the §20.2 domains and §20.4 stages stay verbatim and ordered",
                check=plan_vocabularies,
            ),
            Criterion(
                id="software-pyproject-integrity",
                domain=self.domain,
                description="pyproject.toml agrees with the package and the core stays stdlib-only",
                check=pyproject_integrity,
            ),
        )


# ------------------------------------------------------------- §20.2 windows


class WindowsVerifier(BaseVerifier):
    """The *Windows* domain — Windows facts are judged on the real box."""

    id = "windows-verifier"
    domain = "windows"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_vocabulary() -> str:
            from nexus import windows as nxwin

            assert nxwin.WINDOWS_SECTIONS, "the windows package lost its §10 sections"
            assert callable(nxwin.WindowRegistry), "WindowRegistry missing"
            return (
                f"nexus.windows · {len(nxwin.WINDOWS_SECTIONS)} sections "
                "· WindowRegistry present"
            )

        def platform_probe() -> str:
            if sys.platform == "win32":
                ver = platform.win32_ver()
                return f"real Windows host: {platform.system()} {ver}"
            raise CriterionSkipped(
                f"host is {platform.system()} — the Windows facts are judged on the real box"
            )

        def checkpoint_probe() -> str:
            checkpoint = Path(os.environ.get("NEXUS_CHECKPOINT", DEFAULT_CHECKPOINT))
            if checkpoint.is_dir():
                entries = sum(1 for _ in checkpoint.iterdir())
                return f"checkpoint {checkpoint} present ({entries} entries)"
            if platform.system() != "Windows":
                raise CriterionSkipped(
                    f"checkpoint {checkpoint} not mounted on this "
                    f"{platform.system()} host"
                )
            raise AssertionError(f"checkpoint {checkpoint} missing on a Windows host")

        def powershell_probe() -> str:
            ps = shutil.which("powershell") or shutil.which("pwsh")
            if ps:
                return f"powershell available: {ps}"
            if platform.system() != "Windows":
                raise CriterionSkipped("no powershell on this host — honest null")
            raise AssertionError("no powershell on a Windows host")

        return (
            Criterion(
                id="windows-package-vocabulary",
                domain=self.domain,
                description="the §10 window-manager package is present with its sections",
                check=package_vocabulary,
            ),
            Criterion(
                id="windows-platform-probe",
                domain=self.domain,
                description="the host platform is observed and named honestly",
                check=platform_probe,
            ),
            Criterion(
                id="windows-checkpoint-probe",
                domain=self.domain,
                description="the M:\\NEXUS checkpoint is probed where it can exist",
                check=checkpoint_probe,
            ),
            Criterion(
                id="windows-powershell-probe",
                domain=self.domain,
                description="a PowerShell binary is probed where it can exist",
                check=powershell_probe,
            ),
        )


# ------------------------------------------------------------- §20.2 browser


class BrowserVerifier(BaseVerifier):
    """The *Browser* domain — vocabulary everywhere, engine where installed."""

    id = "browser-verifier"
    domain = "browser"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_vocabulary() -> str:
            from nexus import browser as nxb

            assert nxb.BROWSER_OPERATIONS, "browser operations lost"
            assert nxb.CHANNEL_LADDER, "the channel ladder lost"
            assert callable(nxb.PlaywrightEngine), "PlaywrightEngine missing"
            return (
                f"{len(nxb.BROWSER_OPERATIONS)} operations · "
                f"{len(nxb.CHANNEL_LADDER)} channel-ladder rungs · PlaywrightEngine present"
            )

        def engine_probe() -> str:
            spec = importlib.util.find_spec("playwright")
            if spec is None:
                raise CriterionSkipped("playwright not installed on this host — honest null")
            return "playwright importable — the §11.1 MODE A engine is present"

        return (
            Criterion(
                id="browser-package-vocabulary",
                domain=self.domain,
                description="the §11 browser runtime exports its operations and ladder",
                check=package_vocabulary,
            ),
            Criterion(
                id="browser-engine-probe",
                domain=self.domain,
                description="playwright availability is probed, never assumed",
                check=engine_probe,
            ),
        )


# ----------------------------------------------------------- §20.2 documents


class DocumentsVerifier(BaseVerifier):
    """The *Documents* domain — §18's floors without inventing engines."""

    id = "documents-verifier"
    domain = "documents"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_vocabulary() -> str:
            from nexus import documents as nxd

            assert len(nxd.DOCUMENT_KINDS) >= 3, (
                f"expected docx/pptx/pdf kinds, got {nxd.DOCUMENT_KINDS}"
            )
            assert nxd.PIPELINE_STAGES, "document pipeline stages lost"
            assert callable(nxd.DocumentVerification), "DocumentVerification missing"
            return (
                f"{len(nxd.DOCUMENT_KINDS)} document kinds · "
                f"{len(nxd.PIPELINE_STAGES)} pipeline stages · DocumentVerification present"
            )

        def backend_probe() -> str:
            spec = importlib.util.find_spec("docling")
            if spec is None:
                raise CriterionSkipped(
                    "docling not installed — the native stdlib floors "
                    "keep documents flowing"
                )
            return "docling importable — the §18 heavy backend is present"

        return (
            Criterion(
                id="documents-package-vocabulary",
                domain=self.domain,
                description="the §18 package exposes its kinds, stages and verification contract",
                check=package_vocabulary,
            ),
            Criterion(
                id="documents-backend-probe",
                domain=self.domain,
                description="docling availability is probed honestly (MODE A/B law)",
                check=backend_probe,
            ),
        )


# ------------------------------------------------------------ §20.2 research


class ResearchVerifier(BaseVerifier):
    """The *Research* domain — §17's runtime surface is really there."""

    id = "research-verifier"
    domain = "research"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_vocabulary() -> str:
            from nexus import research as nxr

            assert nxr.CONFIDENCE_DIMENSIONS, "confidence dimensions lost"
            assert callable(nxr.ResearchEngine), "ResearchEngine missing"
            assert callable(nxr.EvidenceItem), "EvidenceItem missing"
            assert callable(nxr.Finding), "Finding missing"
            return (
                f"{len(nxr.CONFIDENCE_DIMENSIONS)} confidence dimensions · "
                f"ResearchEngine · EvidenceItem · Finding present"
            )

        def authority_map() -> str:
            from nexus import research as nxr

            assert nxr.AUTHORITY_BY_CLASS, "the authority map lost"
            classes = sorted(nxr.AUTHORITY_BY_CLASS)[:4]
            return (
                f"authority map holds {len(nxr.AUTHORITY_BY_CLASS)} classes, "
                f"e.g. {', '.join(classes)}"
            )

        def providers_present() -> str:
            from nexus import research as nxr

            for name in ("LocalSearchProvider", "GitHubSearchProvider", "DocsSearchProvider"):
                assert callable(getattr(nxr, name, None)), f"{name} missing"
            return "LocalSearchProvider · GitHubSearchProvider · DocsSearchProvider present"

        return (
            Criterion(
                id="research-package-vocabulary",
                domain=self.domain,
                description="the §17 engine, evidence and finding contracts are present",
                check=package_vocabulary,
            ),
            Criterion(
                id="research-authority-map",
                domain=self.domain,
                description="the authority-by-class map is populated",
                check=authority_map,
            ),
            Criterion(
                id="research-providers-present",
                domain=self.domain,
                description="the search providers are declared",
                check=providers_present,
            ),
        )


# ------------------------------------------------------------------ §20.2 git


class GitVerifier(BaseVerifier):
    """The *Git* domain — a real binary, a real HEAD, a real sha."""

    id = "git-verifier"
    domain = "git"

    def criteria(self) -> tuple[Criterion, ...]:
        def binary_probe() -> str:
            git = shutil.which("git")
            assert git, "no git binary on PATH — §16 operations cannot run"
            return f"git binary: {git}"

        def repo_root_probe() -> str:
            import nexus

            root = Path(nexus.__file__).resolve().parent.parent
            cursor = root
            for _ in range(6):
                if (cursor / ".git").exists():
                    sha = _head_sha(cursor)
                    return f"repo root {cursor} · HEAD {sha[:12]}"
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent
            raise CriterionSkipped(
                "no .git above the package — the deployed tree is not a repo here"
            )

        def engine_vocabulary() -> str:
            from nexus import git as nxg

            assert nxg.GIT_OPERATIONS, "git operations lost"
            assert nxg.LIFECYCLE_STAGES, "lifecycle stages lost"
            assert callable(nxg.GitEngine), "GitEngine missing"
            return (
                f"{len(nxg.GIT_OPERATIONS)} operations · "
                f"{len(nxg.LIFECYCLE_STAGES)} lifecycle stages · GitEngine present"
            )

        return (
            Criterion(
                id="git-binary-probe",
                domain=self.domain,
                description="a real git binary is on PATH",
                check=binary_probe,
            ),
            Criterion(
                id="git-repo-root-probe",
                domain=self.domain,
                description="the package sits in a real git repo (HEAD read with stdlib)",
                check=repo_root_probe,
            ),
            Criterion(
                id="git-engine-vocabulary",
                domain=self.domain,
                description="the §16 GitEngine surface is present",
                check=engine_vocabulary,
            ),
        )


def _head_sha(repo_root: Path) -> str:
    """Read HEAD's sha straight from .git with stdlib (no subprocess)."""
    head = (repo_root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        ref_path = repo_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()
        packed = repo_root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.strip().endswith(ref):
                    return line.split()[0]
        raise AssertionError(f"ref {ref} not resolvable under {repo_root}")
    return head


# --------------------------------------------------------------- §20.2 memory


class MemoryVerifier(BaseVerifier):
    """The *Memory* domain — a real §12 engine roundtrip, closed cleanly."""

    id = "memory-verifier"
    domain = "memory"

    def criteria(self) -> tuple[Criterion, ...]:
        def engine_roundtrip() -> str:
            from nexus.memory import MemoryEngine, SQLiteMemoryStore

            tmp = Path(tempfile.mkdtemp(prefix="nexus-verify-mem-"))
            try:
                engine = MemoryEngine(SQLiteMemoryStore(tmp / "m.db"))
                try:
                    record = engine.remember(
                        "phase-20 verification probe — the memory domain proves itself",
                        type="fact",
                        source="verification-probe",
                    )
                    context = engine.retrieve("phase-20 verification probe")
                    blocks = getattr(context, "blocks", ())
                    assert any(
                        "verification probe" in (getattr(b, "text", "") or "") for b in blocks
                    ), "the remembered fact did not come back"
                finally:
                    engine.close()  # the Windows handle lesson: close BEFORE cleanup
                return f"remembered {record.id} · retrieved {len(blocks)} block(s) · engine closed"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def evidence_vocabulary() -> str:
            from nexus import memory as nxm

            assert nxm.EVIDENCE_FIELDS, "the §12 evidence fields lost"
            assert nxm.EVIDENCE_METHODS, "the §12 evidence methods lost"
            assert callable(nxm.MemoryEvidence), "MemoryEvidence missing"
            return (
                f"{len(nxm.EVIDENCE_FIELDS)} evidence fields · "
                f"{len(nxm.EVIDENCE_METHODS)} evidence methods · MemoryEvidence present"
            )

        return (
            Criterion(
                id="memory-engine-roundtrip",
                domain=self.domain,
                description="a real §12 engine remembers and retrieves, then closes cleanly",
                check=engine_roundtrip,
            ),
            Criterion(
                id="memory-evidence-vocabulary",
                domain=self.domain,
                description="the §12 evidence fields and methods stay declared",
                check=evidence_vocabulary,
            ),
        )


# -------------------------------------------------------------- §20.2 models


class ModelsVerifier(BaseVerifier):
    """The *Models* domain — the runtime is probed, the provenance is law."""

    id = "models-verifier"
    domain = "models"

    def criteria(self) -> tuple[Criterion, ...]:
        def package_vocabulary() -> str:
            from nexus import models as nxm

            assert nxm.ALL_CAPABILITIES, "model capabilities lost"
            assert nxm.FORMAT_GGUF, "the gguf format constant lost"
            assert callable(nxm.LoadedModel), "LoadedModel missing"
            return (
                f"{len(nxm.ALL_CAPABILITIES)} capabilities · "
                f"format {nxm.FORMAT_GGUF} · LoadedModel present"
            )

        def runtime_probe() -> str:
            from nexus.models import DEFAULT_BINARY

            candidates = [Path(DEFAULT_BINARY)]
            found = [c for c in candidates if c.exists()] or (
                [Path(p) for p in (shutil.which("llama-cli"), shutil.which("llama-server")) if p]
            )
            if not found:
                raise CriterionSkipped("no local llama.cpp runtime on this host — honest null")
            return f"runtime binary present: {found[0]}"

        def benchmark_provenance() -> str:
            from nexus import models as nxm

            assert nxm.BENCHMARK_SOURCE_MEASURED, "the measured-source constant lost"
            assert nxm.BENCHMARK_SOURCE_MIMO_EDGE, "the mimo-edge-source constant lost"
            assert nxm.BENCHMARK_SOURCE_MEASURED != nxm.BENCHMARK_SOURCE_MIMO_EDGE, (
                "a measured row must be distinguishable from a documented row"
            )
            return (
                f"sources distinguished: {nxm.BENCHMARK_SOURCE_MEASURED!r} "
                f"vs {nxm.BENCHMARK_SOURCE_MIMO_EDGE!r}"
            )

        return (
            Criterion(
                id="models-package-vocabulary",
                domain=self.domain,
                description="the §5 model runtime exports its capabilities and contracts",
                check=package_vocabulary,
            ),
            Criterion(
                id="models-runtime-probe",
                domain=self.domain,
                description="a llama.cpp binary is probed, never assumed",
                check=runtime_probe,
            ),
            Criterion(
                id="models-benchmark-provenance",
                domain=self.domain,
                description="measured and documented benchmark rows stay distinguished",
                check=benchmark_provenance,
            ),
        )


# -------------------------------------------------------------- §20.2 system


class SystemVerifier(BaseVerifier):
    """The *System* domain — the host is measured, not described."""

    id = "system-verifier"
    domain = "system"

    def criteria(self) -> tuple[Criterion, ...]:
        def python_floor() -> str:
            assert sys.version_info >= (3, 11), (
                f"python {sys.version_info[:3]} below the 3.11 floor"
            )
            return f"python {sys.version_info[:3]} on {platform.system()} {platform.release()}"

        def temp_writable() -> str:
            tmp = Path(tempfile.mkdtemp(prefix="nexus-verify-sys-"))
            try:
                probe = tmp / "probe.txt"
                probe.write_text("verification", encoding="utf-8")
                read_back = probe.read_text(encoding="utf-8")
                assert read_back == "verification", "the temp file did not read back"
                return f"temp write/read OK ({len(read_back)} bytes) in {tmp.name}"
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def disk_free() -> str:
            usage = shutil.disk_usage(tempfile.gettempdir())
            assert usage.free > 0, "no free disk space reported"
            return f"{usage.free / (1024 ** 3):.1f} GiB free on the temp volume"

        def resources_observable() -> str:
            cpus = os.cpu_count()
            assert cpus and cpus > 0, "cpu_count produced nothing"
            assert platform.system(), "platform.system() empty"
            return f"{cpus} logical CPUs · {platform.machine()}"

        return (
            Criterion(
                id="system-python-floor",
                domain=self.domain,
                description="the interpreter meets the 3.11 floor",
                check=python_floor,
            ),
            Criterion(
                id="system-temp-writable",
                domain=self.domain,
                description="a real temp file is written and read back",
                check=temp_writable,
            ),
            Criterion(
                id="system-disk-free",
                domain=self.domain,
                description="the temp volume reports free space",
                check=disk_free,
            ),
            Criterion(
                id="system-resources-observable",
                domain=self.domain,
                description="CPU count and architecture are observable",
                check=resources_observable,
            ),
        )


# ------------------------------------------------------------------ factory


#: The nine built-in verifiers, in §20.2 order.
_VERIFIER_FACTORIES: tuple[type[BaseVerifier], ...] = (
    SoftwareVerifier,
    WindowsVerifier,
    BrowserVerifier,
    DocumentsVerifier,
    ResearchVerifier,
    GitVerifier,
    MemoryVerifier,
    ModelsVerifier,
    SystemVerifier,
)


def make_verifiers(store: EvidenceStore | None = None) -> tuple[Verifier, ...]:
    """All nine §20.2 verifiers, in the plan's order, sharing one store."""
    return tuple(factory(store) for factory in _VERIFIER_FACTORIES)


__all__ = [
    "BaseVerifier",
    "BrowserVerifier",
    "DocumentsVerifier",
    "GitVerifier",
    "MemoryVerifier",
    "ModelsVerifier",
    "ResearchVerifier",
    "SoftwareVerifier",
    "SystemVerifier",
    "WindowsVerifier",
    "make_verifiers",
]
