# -*- coding: utf-8 -*-
"""NEXUS Skill System — PHASE 31 — bootstrap content (stdlib only).

Everything the worker needs to demonstrate the three lifecycle paths with
REAL disk evidence:
  CREATE   three skills born via create_skill() (§83 direct path)
  IMPORT   one foreign package staged in skills\\staging\\ then imported
           byte-identically with full provenance
  LEARN    observations appended to observations.jsonl; one stream passes
           the §84 gate (repeated/useful/verifiable/not-temporary) and is
           promoted to a REGISTERED skill; one stream is honestly REJECTED
           with named reasons (single occurrence + temporary_info=true)

Bootstrap is idempotent: nothing existing is ever overwritten (PHASE 30
lesson 3) and observations are appended only up to their target count.
"""
from __future__ import annotations

from pathlib import Path

from skill_common import append_jsonl, atomic_json, read_jsonl, utcnow
from skill_manager import SkillError, SkillStore

SPEC_NOTE_ORGANIZER = {
    "name": "note-organizer",
    "version": "1.0.0",
    "description": "يحفظ ملاحظة داخل سجل تشغيل محصور مع فهرسة في journal",
    "inputs": {
        "title": {"type": "string", "required": True,
                  "description": "اسم الملاحظة (يُستخدم كاسم ملف)"},
        "body": {"type": "string", "required": True,
                 "description": "نص الملاحظة"},
    },
    "tools": ["write_note", "append_journal"],
    "workflow": [
        {"op": "write_note", "name": "{{input.title}}.txt",
         "text": "{{input.body}}"},
        {"op": "append_journal",
         "text": "note '{{input.title}}' filed"},
    ],
    "verification": "outputs_hashed_and_files_exist_in_jail",
    "source": "created",
    "executable": True,
}

SPEC_TEXT_SUMMARIZE = {
    "name": "text-summarize",
    "version": "1.0.0",
    "description": "قالب ملخص قابل لإعادة الاستخدام (§82 render-only)",
    "inputs": {
        "text": {"type": "string", "required": True,
                 "description": "النص المدخل"},
        "count": {"type": "string", "required": True,
                  "description": "عدد النقاط المطلوبة"},
    },
    "tools": [],
    "workflow": [
        {"op": "prompt",
         "text": "لخص النص التالي في {{input.count}} نقاط مع الحفاظ على "
                 "المصطلحات:\n\n{{input.text}}"},
    ],
    "verification": "rendered_prompt_contains_inputs",
    "source": "created",
    "executable": False,
}

SPEC_WORKSPACE_REPORT = {
    "name": "workspace-report",
    "version": "1.0.0",
    "description": "تقرير حالة مساحة عمل بقالب ثابت (render-only)",
    "inputs": {
        "workspace": {"type": "string", "required": True,
                      "description": "مسار مساحة العمل"},
        "files_count": {"type": "string", "required": True,
                        "description": "عدد الملفات المرصودة"},
    },
    "tools": [],
    "workflow": [
        {"op": "prompt",
         "text": "تقرير مساحة العمل {{input.workspace}} — عدد الملفات: "
                 "{{input.files_count}}. التوصية: القرص يحكم — راجع "
                 "المجلدات الكبيرة قبل أي حذف."},
    ],
    "verification": "rendered_report_contains_markers",
    "source": "created",
    "executable": False,
}

CREATE_SPECS = [SPEC_NOTE_ORGANIZER, SPEC_TEXT_SUMMARIZE,
                SPEC_WORKSPACE_REPORT]

FOREIGN_NAME = "download-sorter"
FOREIGN_MANIFEST = {
    "name": FOREIGN_NAME,
    "version": "1.2.0",
    "description": "حزمة أجنبية واردة من خارج المتجر — تُستورد بهوية "
                   "بايت-ببايت وأصل مُسجل (provenance)",
    "inputs": {
        "folder": {"type": "string", "required": True,
                   "description": "المجلد المراد فرزه"},
    },
    "tools": ["echo", "append_journal"],
    "workflow": [
        {"op": "echo", "text": "sort plan for {{input.folder}}"},
        {"op": "append_journal", "text": "scanned {{input.folder}}"},
    ],
    "verification": "echo_marker_and_journal_present",
    "source": "imported",
    "executable": True,
}

GOOD_KEY = "organize-downloads"
TEMP_KEY = "temp-cache-cleanup"
OBS_TARGETS = {GOOD_KEY: 3, TEMP_KEY: 1}

OBS_GOOD = {
    "repeat_key": GOOD_KEY,
    "summary": "تنظيم مجلد التنزيلات: فهرسة + تدوين في سجل — نمط متكرر "
               "مفيد وقابل للتحقق",
    "steps": [
        {"op": "write_note", "name": "downloads-index.txt",
         "text": "files sorted by type"},
        {"op": "append_journal", "text": "downloads organized"},
    ],
    "useful": True, "verifiable": True, "temporary_info": False,
    "actor": "phase31-observer",
}
OBS_TEMP = {
    "repeat_key": TEMP_KEY,
    "summary": "تنظيف كاش مرتبط بجلسة اليوم فقط — معلومة مؤقتة",
    "steps": [{"op": "echo", "text": "cleaned temp cache of this session"}],
    "useful": True, "verifiable": True, "temporary_info": True,
    "actor": "phase31-observer",
}

SAMPLE_INPUTS = {
    "note-organizer": {"title": "meeting-notes",
                       "body": "NEXUS PHASE 31 — skill run evidence"},
    "text-summarize": {"text": "NEXUS يجمع المواصفة والتنفيذ والبرهان في "
                               "حلقة واحدة على القرص.", "count": "3"},
    "workspace-report": {"workspace": "M:/NEXUS-Test",
                         "files_count": "128"},
    FOREIGN_NAME: {"folder": "Downloads"},
    GOOD_KEY: {},
}


def bootstrap(home: Path, log=print) -> dict:
    """Idempotent content bootstrap. Returns what was actually written."""
    store = SkillStore(home)
    out = {"created": [], "staged": [], "observed": {}}

    # 1) CREATE the three sample skills (never overwrite)
    for spec in CREATE_SPECS:
        d = store.store / spec["name"]
        if not (d / "skill.json").is_file():
            try:
                reg = store.create_skill(spec, actor="phase31-bootstrap",
                                         source="created")
                out["created"].append(reg["name"])
                log(f"bootstrap created {reg['name']}")
            except SkillError as exc:
                out.setdefault("create_errors", []).append(
                    f"{spec['name']}: {exc}")

    # 2) STAGE the foreign package (import source, written only if missing)
    fdir = store.staging / FOREIGN_NAME
    fdir.mkdir(parents=True, exist_ok=True)
    fpath = fdir / "skill.json"
    if not fpath.is_file():
        atomic_json(fpath, FOREIGN_MANIFEST)
        out["staged"].append(FOREIGN_NAME)
        log(f"bootstrap staged {FOREIGN_NAME}")

    # 3) OBSERVE — append only up to target counts (idempotent across boots)
    existing = {}
    for o in read_jsonl(store.observations_path):
        k = o.get("repeat_key")
        existing[k] = existing.get(k, 0) + 1
    for obs, key in ((OBS_GOOD, GOOD_KEY), (OBS_TEMP, TEMP_KEY)):
        target = OBS_TARGETS[key]
        have = existing.get(key, 0)
        need = target - have
        if key not in out["observed"]:
            out["observed"][key] = {"have": have, "target": target,
                                    "appended": 0}
        for i in range(max(0, need)):
            entry = dict(obs)
            entry["utc"] = utcnow()
            entry["seq"] = have + i + 1
            append_jsonl(store.observations_path, entry)
            out["observed"][key]["appended"] += 1
        if need > 0:
            log(f"bootstrap observed {key} +{need}")
    return out
