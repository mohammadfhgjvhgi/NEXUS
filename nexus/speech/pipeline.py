"""Voice pipeline (New Plan §19.4) — verbatim, a verdict per stage.

    Microphone → STT → Normalization → Intent → Task

* *Microphone* is the :class:`AudioSource` — a real captured utterance
  enters here (``FileAudioSource`` is the proven floor; a live mic
  needs a host audio stack and says so honestly).
* *STT* is the §19.1 provider's ``transcribe``.
* *Normalization* is the §19.4 normalizer (one law for Arabic,
  English and the mixed shapes).
* *Intent* is the bilingual router's verdict.
* *Task* lands a real :class:`VoiceTask` — and when a §12 memory sink
  is attached, the task is *remembered with its provenance* before the
  verdict is issued.

Every stage records a :class:`StageTrace` (ok / failed / pending);
the first failure stops the run and the traces tell the truth about
how far the utterance got.
"""

from __future__ import annotations

from typing import Any

from .contracts import (
    INTENT_TO_TASK_KIND,
    PIPELINE_STAGES,
    AudioInput,
    ProviderUnavailableError,
    SpeechError,
    SpeechProvider,
    StageState,
    StageTrace,
    VoiceTask,
)
from .intent import INTENT_UNKNOWN, IntentResult, IntentRouter
from .textnorm import normalize_text


class AudioSource:
    """The *Microphone* stage — one captured utterance per ``capture``."""

    name = "source"

    def capture(self) -> AudioInput:
        raise NotImplementedError


class FileAudioSource(AudioSource):
    """The proven floor — a real utterance already captured (fixtures,
    recordings, the SAPI file path)."""

    name = "file"

    def __init__(self, audio: AudioInput) -> None:
        self._audio = audio

    def capture(self) -> AudioInput:
        return self._audio


class MicAudioSource(AudioSource):
    """The live microphone — honest about what it needs.

    Live capture requires a host audio stack (the MODE B install's
    device layer, or SAPI's live-recognition session with user
    consent).  This floor refuses clearly instead of pretending.
    """

    name = "microphone"

    def capture(self) -> AudioInput:
        raise ProviderUnavailableError(
            "live microphone capture needs a host audio stack — the "
            "proven phase-19 path is FileAudioSource over captured WAV; "
            "wire the device audio layer here when it lands"
        )


class VoicePipeline:
    """The five §19.4 stages, in order, one honest trace each."""

    stages: tuple[str, ...] = PIPELINE_STAGES

    def __init__(
        self,
        provider: SpeechProvider,
        *,
        router: IntentRouter | None = None,
        source: AudioSource | None = None,
        memory_sink: Any = None,
    ) -> None:
        if provider is None:
            raise SpeechError("VoicePipeline needs a SpeechProvider")
        self._provider = provider
        self._router = router or IntentRouter()
        self._source = source
        self._memory = memory_sink

    def run(self, audio: AudioInput | None = None) -> PipelineResult:
        """One utterance through the five stages — verdicts, not hopes."""
        traces: list[StageTrace] = []

        def fail(stage: str, exc: Exception) -> PipelineResult:
            traces.append(StageTrace(stage, StageState.FAILED, f"{type(exc).__name__}: {exc}"))
            traces.extend(
                StageTrace(name, StageState.PENDING) for name in self.stages[len(traces):]
            )
            return PipelineResult(task=None, traces=tuple(traces))

        # 1 — microphone: the utterance enters
        try:
            if audio is not None:
                # an explicit utterance overrides the source — documented
                source: AudioSource = FileAudioSource(audio)
            elif self._source is not None:
                source = self._source
            else:
                raise SpeechError("no utterance given and no source configured")
            captured = source.capture()
            if not isinstance(captured, AudioInput):
                raise SpeechError(
                    f"source {source.name!r} returned {type(captured).__name__}, "
                    "not an AudioInput"
                )
        except Exception as exc:  # noqa: BLE001
            return fail("microphone", exc)
        traces.append(
            StageTrace(
                "microphone",
                StageState.OK,
                f"{captured.source_uri} ({captured.duration_seconds:.2f}s)",
            )
        )

        # 2 — stt: the provider's transcribe
        try:
            transcription = self._provider.transcribe(captured)
            if not transcription.text.strip():
                raise SpeechError("provider returned an empty transcript")
        except Exception as exc:  # noqa: BLE001
            return fail("stt", exc)
        traces.append(
            StageTrace(
                "stt",
                StageState.OK,
                f"{transcription.provider}: {transcription.text[:60]!r}",
            )
        )

        # 3 — normalization: one law for ar / en / mixed
        try:
            normalized = normalize_text(transcription.text)
            if not normalized:
                raise SpeechError("normalization produced an empty line")
        except Exception as exc:  # noqa: BLE001
            return fail("normalization", exc)
        traces.append(StageTrace("normalization", StageState.OK, normalized[:60]))

        # 4 — intent: the bilingual verdict
        try:
            verdict = self._router.route(normalized)
        except Exception as exc:  # noqa: BLE001
            return fail("intent", exc)
        traces.append(
            StageTrace(
                "intent",
                StageState.OK,
                f"{verdict.intent} ({verdict.confidence:.2f})",
            )
        )

        # 5 — task: a real NEXUS task, remembered with provenance
        task = VoiceTask(
            utterance=transcription.text,
            normalized_text=normalized,
            language=transcription.language,
            intent=verdict.intent,
            confidence=verdict.confidence,
            argument=verdict.argument,
            task_kind=INTENT_TO_TASK_KIND.get(verdict.intent, "unclassified"),
            provider=transcription.provider,
            audio_uri=captured.source_uri,
        )
        detail = f"{task.task_kind} built"
        if self._memory is not None and verdict.intent != INTENT_UNKNOWN:
            try:
                self._memory.remember_task(
                    task,
                    transcript=transcription.text,
                    provider=transcription.provider,
                )
                detail = f"{task.task_kind} built + remembered"
            except Exception as exc:  # noqa: BLE001 — memory fails, task stands
                detail = f"{task.task_kind} built (memory refused: {exc})"
        traces.append(StageTrace("task", StageState.OK, detail))
        return PipelineResult(task=task, traces=tuple(traces))


class PipelineResult:
    """The run's product — the task (when it landed) and the traces."""

    def __init__(self, task: VoiceTask | None, traces: tuple[StageTrace, ...]) -> None:
        self.task = task
        self.traces = traces

    @property
    def ok(self) -> bool:
        return bool(self.traces) and all(t.state == StageState.OK for t in self.traces)

    @property
    def intent_result(self) -> IntentResult | None:
        """Reconstruct the router's verdict from the task — for callers
        that want the raw intent row without re-routing."""
        if self.task is None:
            return None
        return IntentResult(
            intent=self.task.intent,
            confidence=self.task.confidence,
            argument=self.task.argument,
            normalized_text=self.task.normalized_text,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "task": self.task.as_dict() if self.task is not None else None,
            "traces": [t.as_dict() for t in self.traces],
        }
