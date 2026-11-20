# NEXUS — Known Issues (New Plan §59)

Problems **outside the current phase's scope** live here — they never
silently become new tasks. An issue leaves this file when its owning
phase (or a hotfix) resolves it.

| Id | Raised | Issue | Owning phase / status |
|---|---|---|---|
| KI-1 | Phase 11 | Device §12.5 OCR race still awaits the operator's one-command install (`winget tesseract` + optional `pip winsdk`) — gatekeeper blocks agent-side installs by design; `proofs\\run_live.bat` is staged and extends PATH | Phase 11 close-out — **operator action pending** |
| KI-2 | Phase 11 | `ModelVisionProvider` is a stub on the device (no vision-capable model loaded yet) — the vision rung degrades honestly to OCR/input | resolved when a VLM lands (PHASE 32 / Midpoint+ models) |
| KI-3 | Sandbox | The sandbox rebuilt twice during Phases 11–12; untracked trees (`vendor-staging/`, `repo-stage/`, `.credentials/`) vanish on rebuild — git-tracked state (worklog, tools/) survives by design | environmental — mitigated by the tunnel PAT recovery flow |
