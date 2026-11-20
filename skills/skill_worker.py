# -*- coding: utf-8 -*-
"""NEXUS Skill System — PHASE 31 — detached worker & certification.

Spawned ONCE via the pytest trigger (skills\\test_phase31_spawn.py),
DETACHED so it survives tunnel death. Read-only polling afterwards.

Lifecycle (§82/§83/§84 — evidence or silence):
  bootstrap   write sample skills + stage foreign package + observations
              (idempotent, never overwrites)
  import      byte-identical import of the staged package + provenance
  learn       §84 gate: promote organize-downloads (3 obs, passes) and
              attempt temp-cache-cleanup (1 obs, temporary) -> honest
              REJECTED with named reasons
  selftest    render EVERY skill; run every executable skill inside the
              run jail; hash every output
  certify     registry.json + proofs\\phase31_skills.json; verdict:
              PASS | PASS_WITH_DEGRADATION (integration) | FAIL
  resident    rescan 30s (hot-adopt new skill packages), heartbeat 10s,
              STOP file = clean exit
"""
from __future__ import annotations

import calendar
import faulthandler
import json
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent          # M:\NEXUS\skills
ROOT = HERE.parent                              # M:\NEXUS
PROOFS = ROOT / "proofs"
sys.path.insert(0, str(HERE))

from skill_common import PHASE, VERSION, atomic_json, utcnow  # noqa: E402
import skill_manager  # noqa: E402
import skill_samples  # noqa: E402

HB_PATH = HERE / ".hb.json"
REGISTRY_PATH = HERE / "registry.json"
RESULT_PATH = HERE / "worker_phase31.result.json"
EVIDENCE_PATH = PROOFS / "phase31_skills.json"
STOP_PATH = HERE / "STOP"
LOG_PATH = HERE / "worker_phase31.log"
RESCAN_S = 30.0

_T0 = time.time()
_state = {"selftest": "not_started", "skills_total": 0, "counts": {}}
_state_lock = threading.Lock()


def _set_state(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def write_hb() -> None:
    import os
    obj = {"utc": utcnow(), "phase": PHASE, "version": VERSION,
           "pid": os.getpid(), "uptime_s": round(time.time() - _T0, 1),
           "running": True}
    with _state_lock:
        obj.update({k: _state.get(k) for k in
                    ("selftest", "skills_total", "counts")})
    atomic_json(HB_PATH, obj)


def _hb_loop() -> None:
    while True:
        try:
            write_hb()
        except BaseException:
            pass
        time.sleep(10.0)


def _hb_fresh() -> bool:
    try:
        hb = json.loads(HB_PATH.read_text(encoding="utf-8"))
        age = time.time() - calendar.timegm(
            time.strptime(hb["utc"], "%Y-%m-%dT%H:%M:%SZ"))
        return age < 90 and hb.get("running") is True
    except BaseException:
        return False


def _module_hashes() -> dict:
    out = {}
    for name in ("skill_common.py", "skill_manager.py", "skill_samples.py",
                 "skill_worker.py"):
        p = HERE / name
        if p.is_file():
            out[name] = {"size": p.stat().st_size, "sha256": skill_manager.sha256_file(p)}
    return out


def _cross_system() -> dict:
    """Honest snapshot of sibling systems (plugins / realtime)."""
    snap = {"plugins": {"registry_present": False},
            "realtime": {"hb_present": False}}
    preg = ROOT / "plugins" / "registry.json"
    if preg.is_file():
        try:
            data = json.loads(preg.read_text(encoding="utf-8"))
            snap["plugins"] = {
                "registry_present": True,
                "generated_utc": data.get("generated_utc"),
                "loaded_total": data.get("loaded_total"),
                "counts_by_type": data.get("counts_by_type"),
            }
        except BaseException as exc:
            snap["plugins"] = {"registry_present": True,
                               "error": f"{type(exc).__name__}"}
    rhb = ROOT / "realtime" / ".hb.json"
    if rhb.is_file():
        try:
            data = json.loads(rhb.read_text(encoding="utf-8"))
            age = time.time() - calendar.timegm(time.strptime(
                data.get("utc", utcnow()), "%Y-%m-%dT%H:%M:%SZ"))
            chans = data.get("channels") or {}
            snap["realtime"] = {
                "hb_present": True, "hb_utc": data.get("utc"),
                "hb_age_s": round(age, 1), "hb_running": data.get("running"),
                "pid": data.get("pid"),
                "channels_up": sorted(k for k, v in chans.items()
                                      if isinstance(v, dict) and v.get("up")),
            }
        except BaseException as exc:
            snap["realtime"] = {"hb_present": True,
                                "error": f"{type(exc).__name__}"}
    return snap


def _integration(home: Path, skills_total: int) -> dict:
    """PHASE 29 events channel :9412 round-trip — honest either way."""
    try:
        r = skill_manager.events_pub(home, {
            "type": "phase31.skills",
            "data": {"marker": "nexus31-skills-roundtrip",
                     "skills_total": skills_total}})
    except BaseException as exc:
        return {"verdict": "DEGRADED",
                "detail": {"reason": f"{type(exc).__name__}: {exc}"[:200],
                           "note": "PHASE 29 events channel unreachable "
                                   "(after reboot it stays down until "
                                   "revived)"}}
    eid = r.get("id")
    if not isinstance(eid, int):
        return {"verdict": "FAIL", "detail": {"reply": str(r)[:160]}}
    try:
        v = skill_manager.events_verify(home, eid, "phase31.skills")
    except BaseException as exc:
        return {"verdict": "DEGRADED",
                "detail": {"event_id": eid,
                           "reason": f"verify:{type(exc).__name__}: "
                                     f"{exc}"[:160]}}
    ok = v.get("ok") is True
    return {"verdict": "PASS" if ok else "FAIL",
            "detail": {"event_id": eid, "roundtrip": ok,
                       "stream_count": v.get("count"),
                       "cursor": v.get("cursor")}}


def _selftest(entries: list, store) -> dict:
    """Render every skill; run every executable one in the jail."""
    per = {}
    for e in entries:
        if e.get("status") != "valid":
            per[e["name"]] = {"verdict": "FAIL",
                              "detail": {"errors": e.get("errors")}}
            continue
        inputs = skill_samples.SAMPLE_INPUTS.get(
            e["name"], skill_samples.SAMPLE_INPUTS.get(
                skill_samples.GOOD_KEY, {}))
        try:
            r = store.render_skill(e, inputs)
            if not r["ok"]:
                per[e["name"]] = {"verdict": "FAIL",
                                  "detail": {"render_errors": r["errors"]}}
                continue
            if e.get("executable"):
                run = store.run_skill(e, inputs)
                jailed = all(o["jailed"] for o in run["outputs"])
                hashed = all(o.get("sha256") for o in run["outputs"])
                okd = jailed and hashed and run["outputs"]
                per[e["name"]] = {"verdict": "PASS" if okd else "FAIL",
                                  "detail": {"run_dir": run["run_dir"],
                                             "outputs": len(run["outputs"]),
                                             "jailed": jailed,
                                             "hashed": hashed}}
            else:
                head = json.dumps(r["rendered"], ensure_ascii=False)[:80]
                per[e["name"]] = {"verdict": "PASS",
                                  "detail": {"rendered_head": head}}
        except skill_manager.SkillError as exc:
            per[e["name"]] = {"verdict": "FAIL", "detail": {"error": str(exc)}}
        except BaseException as exc:
            per[e["name"]] = {"verdict": "FAIL",
                              "detail": {"error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:160]}}
    return per


def _verdict(lifecycle: dict, selftest: dict, integration: dict) -> str:
    if lifecycle.get("create", {}).get("verdict") != "PASS":
        return "FAIL"
    if lifecycle.get("import", {}).get("status") not in ("PASS",
                                                         "SKIPPED_ALREADY"):
        return "FAIL"
    if lifecycle.get("learn", {}).get("status") != "PASS":
        return "FAIL"
    if any(v.get("verdict") != "PASS" for v in selftest.values()):
        return "FAIL"
    if integration.get("verdict") == "DEGRADED":
        return "PASS_WITH_DEGRADATION"
    if integration.get("verdict") != "PASS":
        return "FAIL"
    return "PASS"


def main() -> int:
    result = {"phase": PHASE, "version": VERSION, "started_utc": utcnow()}
    _fh_log = open(LOG_PATH, "a", encoding="utf-8")   # faulthandler sink
    faulthandler.dump_traceback_later(150, file=_fh_log)
    store = skill_manager.SkillStore(HERE)
    try:
        if _hb_fresh():
            result["verdict"] = "SKIPPED_ALREADY_RUNNING"
            atomic_json(RESULT_PATH, result)
            return 0
        threading.Thread(target=_hb_loop, daemon=True).start()
        _set_state(selftest="booting")

        # 1) bootstrap (idempotent)
        boot = skill_samples.bootstrap(HERE, log=lambda *a: None)
        result["bootstrap"] = boot
        atomic_json(RESULT_PATH, result)

        # 2) discover
        entries = store.discover()
        names = sorted(e["name"] for e in entries)
        _set_state(skills_total=sum(1 for e in entries
                                    if e.get("status") == "valid"))
        result["discovered"] = names
        atomic_json(RESULT_PATH, result)

        # 3) import (skip when already registered — idempotent restarts)
        imported = {"status": "SKIPPED_ALREADY", "detail": {}}
        if skill_samples.FOREIGN_NAME not in names:
            try:
                reg = store.import_skill(HERE / "staging"
                                         / skill_samples.FOREIGN_NAME,
                                         actor="phase31-worker")
                imported = {"status": "PASS", "detail": reg}
            except skill_manager.SkillError as exc:
                imported = {"status": "FAIL", "detail": {"error": str(exc)}}
            except BaseException as exc:
                imported = {"status": "FAIL",
                            "detail": {"error": f"{type(exc).__name__}: "
                                                f"{exc}"[:160]}}
        else:
            imported = {"status": "SKIPPED_ALREADY",
                        "detail": {"note": "already in store"}}
        result["import"] = imported
        atomic_json(RESULT_PATH, result)

        # 4) learn — §84 gate (promote good stream; expect honest reject)
        learn = {"status": "PASS", "promoted": None, "rejected": None,
                 "skipped": None}
        entries = store.discover()
        names = sorted(e["name"] for e in entries)
        if skill_samples.GOOD_KEY in names:
            learn["skipped"] = {
                "repeat_key": skill_samples.GOOD_KEY,
                "note": "already registered from an earlier boot"}
        else:
            try:
                prom = store.promote_observation(skill_samples.GOOD_KEY)
                learn["promoted"] = prom
                if prom.get("status") != "REGISTERED":
                    learn["status"] = "FAIL"
            except BaseException as exc:
                learn["promoted"] = {"status": "REJECTED",
                                     "reasons": [f"{type(exc).__name__}: "
                                                 f"{exc}"[:160]]}
                learn["status"] = "FAIL"
        try:
            rej = store.promote_observation(skill_samples.TEMP_KEY)
            learn["rejected"] = rej
            if rej.get("status") != "REJECTED":
                learn["status"] = "FAIL"   # a temporary stream MUST reject
        except BaseException as exc:
            learn["rejected"] = {"status": "ERROR",
                                 "reasons": [f"{type(exc).__name__}: "
                                             f"{exc}"[:160]]}
            learn["status"] = "FAIL"
        result["learn"] = learn
        atomic_json(RESULT_PATH, result)
        lifecycle = {
            "create": {"verdict": "PASS" if not boot.get("create_errors")
                       else "FAIL",
                       "detail": boot},
            "import": imported,
            "learn": learn,
        }

        # 5) selftest (render all + run executable ones jailed)
        _set_state(selftest="running")
        entries = store.discover()
        valid = [e for e in entries if e.get("status") == "valid"]
        selftest = _selftest(entries, store)
        result["selftest"] = selftest
        atomic_json(RESULT_PATH, result)

        # 6) cross-system snapshot + integration attempt
        cross = _cross_system()
        integration = _integration(HERE, len(valid))
        result["cross_system"] = cross
        result["integration"] = integration
        atomic_json(RESULT_PATH, result)

        # 7) certify — registry.json + proofs\phase31_skills.json
        registry = store.write_registry(entries, extra={
            "lifecycle": {k: (v.get("status") or v.get("verdict"))
                          for k, v in lifecycle.items()},
            "integration": integration,
            "cross_system": cross,
        })
        verdict = _verdict(lifecycle, selftest, integration)
        evidence = {
            "phase": PHASE,
            "title": "Skill System — importable / learnable / creatable "
                     "(§82/§83/§84)",
            "version": VERSION,
            "identity": {"service": "nexus-skills", "host_hint":
                         "almoutmag-v9"},
            "started_utc": result["started_utc"],
            "finished_utc": utcnow(),
            "skills_root": str(store.store),
            "run_jail": str(store.runs),
            "counts": registry.get("counts"),
            "skills": registry.get("skills"),
            "lifecycle": lifecycle,
            "selftest": selftest,
            "integration": integration,
            "cross_system": cross,
            "modules": _module_hashes(),
            "registry_sha256": skill_manager.sha256_file(REGISTRY_PATH),
            "artifacts": [str(REGISTRY_PATH), str(store.observations_path),
                          str(store.runs)],
            "notes": [
                "spec 82: every manifest carries Description/Inputs/Tools/"
                "Workflow/Verification/Version",
                "spec 83: create+import+observe->promote all evidenced",
                "spec 84: gate = repeated/useful/verifiable/not-temporary; "
                "rejections are named, never silent",
                "resident mode: rescan 30s, heartbeat 10s, STOP exits clean",
            ],
            "verdict": verdict,
        }
        atomic_json(EVIDENCE_PATH, evidence)
        result["verdict"] = verdict
        result["evidence_path"] = str(EVIDENCE_PATH)
        result["registry_counts"] = registry.get("counts")
        atomic_json(RESULT_PATH, result)     # lands BEFORE residency
        _set_state(selftest="done", counts=registry.get("counts", {}),
                   skills_total=registry.get("counts", {}).get("total", 0))
        write_hb()
        faulthandler.cancel_dump_traceback_later()
        try:
            _fh_log.flush()
        except BaseException:
            pass

        # 8) resident: hot-rescan + STOP file
        while True:
            if STOP_PATH.exists():
                STOP_PATH.unlink()
                break
            time.sleep(RESCAN_S)
            fresh = store.discover()
            fresh_names = sorted(e["name"] for e in fresh)
            if fresh_names != names:
                names = fresh_names
                cross = _cross_system()
                integration = _integration(HERE, sum(
                    1 for e in fresh if e.get("status") == "valid"))
                registry = store.write_registry(fresh, extra={
                    "lifecycle": {k: (v.get("status") or v.get("verdict"))
                                  for k, v in lifecycle.items()},
                    "integration": integration,
                    "cross_system": cross,
                })
                _set_state(skills_total=registry.get("counts", {}).get(
                    "total", 0), counts=registry.get("counts", {}))
                result["rescan"] = {"utc": utcnow(), "names": names,
                                    "integration": integration}
                atomic_json(RESULT_PATH, result)
                write_hb()
        write_hb()
        hbtxt = HB_PATH.read_text(encoding="utf-8")
        HB_PATH.write_text(hbtxt.replace('"running": true',
                                         '"running": false'),
                           encoding="utf-8")
        result["stopped_utc"] = utcnow()
        atomic_json(RESULT_PATH, result)
        return 0
    except BaseException as exc:  # noqa: BLE001 — result must ALWAYS land
        result["verdict"] = "FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback_tail"] = traceback.format_exc()[-1500:]
        try:
            atomic_json(RESULT_PATH, result)
        except BaseException:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    _rc = 2
    try:
        _rc = main()
    except BaseException:
        traceback.print_exc()
        _rc = 1
    sys.exit(_rc)
