"""Recovery Ladder + Health Supervisor — §23.3.

    detect
      ↓
    diagnose
      ↓
    retry
      ↓
    alternate method
      ↓
    replan

The ladder is walked one rung at a time and every rung is observable
in the returned :class:`LadderOutcome`:

* ``detect``   — the finding must survive re-confirmation; a refuted
  finding ends the walk honestly (``NOT_CONFIRMED``), never acts.
* ``diagnose`` — a cause with a confidence (pluggable; the default is
  a documented signal → cause table).
* ``retry``    — the same action, once (pluggable; absent = failed
  honestly, the walk climbs).
* ``alternate method`` — a genuinely different way (pluggable).
* ``replan``   — hand the problem to the planner; the ladder's last
  rung is an escalation, not a surrender.

The §22 law rides along: the ``before_rung`` hook fires **before**
every world-mutating rung (retry · alternate method) — the caller
wires it to the §22.2 ``BEFORE_RISKY_CHANGE`` trigger, and if the
checkpoint cannot be captured the rung is refused.  A recovery that
mutates the world without a checkpoint is just a second accident.

The :class:`HealthSupervisor` ties the section together — §23.1
silence and §23.2 loop shapes both become findings, every confirmed
finding walks the ladder, and every walked finding marks its
component ``STALLED`` until the component beats again.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .contracts import (
    MONITORED_COMPONENTS,
    ComponentStatus,
    Diagnosis,
    HealthReport,
    HealthVerdict,
    Heartbeat,
    LadderOutcome,
    MonitoredComponent,
    Observation,
    RecoveryResolution,
    StallFinding,
    StallSignal,
    SupervisorReport,
)
from .heartbeat import HeartbeatMonitor
from .stall import StallDetector

#: the default §23.3 diagnose table — documented, explainable, honest.
DEFAULT_CAUSES: dict[StallSignal, str] = {
    StallSignal.SAME_ACTION: (
        "the same action repeats — the actor is not consuming its own result"
    ),
    StallSignal.SAME_ERROR: "the same error repeats — the fix is not landing",
    StallSignal.SAME_STATE: "the state hash is frozen — nothing changes anymore",
    StallSignal.NO_PROGRESS: (
        "no forward movement across the window — the task stopped advancing"
    ),
}

ConfirmFn = Callable[[StallFinding], bool]
DiagnoseFn = Callable[[StallFinding], Diagnosis]
RungFn = Callable[[StallFinding], bool]
ReplanFn = Callable[[StallFinding], RecoveryResolution | None]
BeforeRungFn = Callable[[str, StallFinding], None]


class RecoveryLadder:
    """§23.3 — five rungs, walked, observable, never silent."""

    def __init__(
        self,
        *,
        confirm: ConfirmFn | None = None,
        diagnose: DiagnoseFn | None = None,
        retry: RungFn | None = None,
        alternate: RungFn | None = None,
        replan: ReplanFn | None = None,
        before_rung: BeforeRungFn | None = None,
    ) -> None:
        self._confirm = confirm
        self._diagnose = diagnose
        self._retry = retry
        self._alternate = alternate
        self._replan = replan
        self._before_rung = before_rung

    # ------------------------------------------------------------ public

    def handle(self, finding: StallFinding) -> LadderOutcome:
        """Walk the ladder for one finding — every rung on the record."""
        # -- detect: the finding must survive re-confirmation
        if self._confirm is not None and not self._confirm(finding):
            return LadderOutcome(
                finding=finding,
                resolution=RecoveryResolution.NOT_CONFIRMED,
                rungs=("detect",),
                stopped_at="detect",
                detail="the finding did not survive re-observation — no action taken",
            )
        rungs = ["detect"]
        notes: list[str] = []

        # -- diagnose
        if self._diagnose is not None:
            diagnosis = self._diagnose(finding)
        else:
            diagnosis = Diagnosis(
                signal=finding.signal,
                cause=DEFAULT_CAUSES[finding.signal],
                confidence=0.5,
            )
        rungs.append("diagnose")

        # -- retry → alternate method (world-mutating rungs)
        for rung_name, rung_fn in (
            ("retry", self._retry),
            ("alternate_method", self._alternate),
        ):
            if rung_fn is None:
                notes.append(f"{rung_name}: not registered — climbed past it")
                rungs.append(rung_name)
                continue
            if not self._announce(rung_name, finding, notes):
                continue  # the §22 gate refused the rung — climb honestly
            rungs.append(rung_name)
            try:
                if rung_fn(finding):
                    notes.append(f"{rung_name}: resolved")
                    return self._outcome(
                        finding,
                        RecoveryResolution.RESOLVED,
                        rungs,
                        rung_name,
                        notes,
                        diagnosis,
                    )
                notes.append(f"{rung_name}: attempted, did not resolve")
            except Exception as exc:  # noqa: BLE001 — a rung failure climbs
                notes.append(f"{rung_name}: raised {type(exc).__name__}: {exc}")

        # -- replan: the last rung hands upward
        rungs.append("replan")
        resolution = RecoveryResolution.REPLAN_NEEDED
        if self._replan is not None:
            try:
                handed = self._replan(finding)
                resolution = (
                    handed if handed is not None else RecoveryResolution.REPLAN_NEEDED
                )
                notes.append("replan: handed to the planner")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"replan: raised {type(exc).__name__}: {exc}")
        else:
            notes.append("replan: no replanner registered — escalated beyond the ladder")
        return self._outcome(
            finding, resolution, rungs, "replan", notes, diagnosis
        )

    # ----------------------------------------------------------- private

    @staticmethod
    def _outcome(
        finding: StallFinding,
        resolution: RecoveryResolution,
        rungs: list[str],
        stopped_at: str,
        notes: list[str],
        diagnosis: Diagnosis,
    ) -> LadderOutcome:
        return LadderOutcome(
            finding=finding,
            resolution=resolution,
            rungs=tuple(rungs),
            stopped_at=stopped_at,
            detail=" · ".join(notes),
            diagnosis=diagnosis,
        )

    def _announce(self, rung_name: str, finding: StallFinding, notes: list[str]) -> bool:
        """The §22 gate — announce a risky rung before it fires.

        A hook that raises refuses the rung: no checkpoint, no risky
        change.  The walk climbs honestly instead.
        """
        if self._before_rung is None:
            return True
        try:
            self._before_rung(rung_name, finding)
            notes.append(f"{rung_name}: announced (§22 before risky change)")
            return True
        except Exception as exc:  # noqa: BLE001 — refuse, never skip silently
            notes.append(
                f"{rung_name}: REFUSED — the §22 announcement failed "
                f"({type(exc).__name__}: {exc})"
            )
            return False


class HealthSupervisor:
    """One poll — §23.1 snapshot + §23.2 windows + §23.3 ladder.

    Each watched component owns a private :class:`StallDetector` (a
    loop is a per-component story — mixing two components' histories
    would hide both).  §23.1 silence becomes a ``no_progress`` finding
    with the truth in its detail: التوقف الصامت is a stall of the
    heartbeat itself.  Every confirmed finding walks the ladder and
    marks its component ``STALLED`` until a fresh beat clears it.
    """

    def __init__(
        self,
        monitor: HeartbeatMonitor,
        ladder: RecoveryLadder,
        *,
        repeat_threshold: int = 3,
        progress_window: int = 8,
    ) -> None:
        self._monitor = monitor
        self._ladder = ladder
        self._repeat = repeat_threshold
        self._window = progress_window
        self._detectors: dict[MonitoredComponent, StallDetector] = {}
        # component → the beat seq whose silence was already reported —
        # a new seq is a new silence era (it spoke, then went silent again)
        self._silent_reported: dict[MonitoredComponent, int] = {}

    # ------------------------------------------------------------ public

    def poll(
        self,
        observations: Mapping[MonitoredComponent | str, Observation] | None = None,
    ) -> SupervisorReport:
        """One heartbeat of the health system itself."""
        report = self._monitor.snapshot()

        pairs: list[tuple[MonitoredComponent, StallFinding]] = []
        obs_map = dict(observations or {})
        for name in MONITORED_COMPONENTS:
            component = MonitoredComponent(name)
            obs = obs_map.get(component) or obs_map.get(name)
            if obs is None:
                continue
            detector = self._detector_for(component)
            for finding in detector.observe(obs):
                pairs.append(
                    (
                        component,
                        StallFinding(
                            signal=finding.signal,
                            repeats=finding.repeats,
                            detail=finding.detail,
                            component=component,
                            at_utc=finding.at_utc,
                        ),
                    )
                )

        for hb in report.components:
            if hb.status is ComponentStatus.SILENT:
                reported_seq = self._silent_reported.get(hb.component)
                if reported_seq is not None and reported_seq == hb.seq:
                    continue  # this silence era is already on the record
                self._silent_reported[hb.component] = hb.seq
                pairs.append(
                    (
                        hb.component,
                        StallFinding(
                            signal=StallSignal.NO_PROGRESS,
                            repeats=0,
                            component=hb.component,
                            detail=(
                                f"heartbeat silent — {hb.component.value} has not "
                                "beaten within the stale window (التوقف الصامت)"
                            ),
                        ),
                    )
                )
            else:
                self._silent_reported.pop(hb.component, None)

        outcomes: list[LadderOutcome] = []
        for _component, finding in pairs:
            outcome = self._ladder.handle(finding)
            outcomes.append(outcome)
            if outcome.resolution is RecoveryResolution.NOT_CONFIRMED:
                continue
            if finding.component is not None:
                self._monitor.mark_stalled(finding.component, detail=finding.detail)
            if outcome.resolution is RecoveryResolution.RESOLVED:
                detector = self._detectors.get(
                    MonitoredComponent(finding.component)
                    if finding.component
                    else None  # type: ignore[arg-type]
                )
                if detector is not None:
                    detector.reset()
        return SupervisorReport(
            health=report,
            findings=tuple(f for _, f in pairs),
            outcomes=tuple(outcomes),
        )

    def detector(self, component: MonitoredComponent | str) -> StallDetector:
        """The component's private detector — callers may reset it."""
        return self._detector_for(MonitoredComponent(component))

    @property
    def monitor(self) -> HeartbeatMonitor:
        return self._monitor

    # ----------------------------------------------------------- private

    def _detector_for(self, component: MonitoredComponent) -> StallDetector:
        detector = self._detectors.get(component)
        if detector is None:
            detector = StallDetector(
                repeat_threshold=self._repeat, progress_window=self._window
            )
            self._detectors[component] = detector
        return detector


def worst_verdict(*reports: HealthReport) -> HealthVerdict:
    """The worst of several snapshot verdicts — folding health upward."""
    order = (HealthVerdict.STALLED, HealthVerdict.DEGRADED, HealthVerdict.HEALTHY)
    for candidate in order:
        if any(r.verdict is candidate for r in reports):
            return candidate
    return HealthVerdict.HEALTHY


def stalled_components(report: HealthReport) -> tuple[Heartbeat, ...]:
    """The §23.1 lines that need attention right now."""
    return tuple(
        hb
        for hb in report.components
        if hb.status in (ComponentStatus.SILENT, ComponentStatus.STALLED)
    )
