# PHASE 27 — Tray + Startup Production (حالة حية)

- utc: 2026-11-19T22:17:47Z
- verdict: **PASS** · sections_ok=True · runtime_ok=True · core=37 pkgs
- exe: NEXUS.exe · 90815683 B · sha256 819d8a9996ec5b2841fde744a97d25d6…
- الشهادة: proofs\phase27_ui.json (8 أقسام بأدلة لكل قسم)
- اللقطات: proofs\phase27\sec_01..06_*.png (لقطة حية لكل مرحلة)
- البوابة مرتبطة: gate_cert_sha256=604e26b360fbc3620f64a4a97e2bcd50…

| # | القسم | البرهان |
|---|---|---|
| 27.1 ico assets | ico | ok=True · {"dir": "M:\\NEXUS\\assets", "files": {"ready": {"size": 2097, "sha256": "03297c740a84b4ac999e"}, "working": {"size": 20 |
| 27.2 production tray | tray | ok=True · {"started": true, "add_ok": true, "load_ok": true, "error": null, "verdicts": {"thread_started": true, "load_big_ok": tr |
| 27.3 state machine | states | ok=True · {"verdicts": {"working": true, "ready": true, "offline": true}, "note": "tooltip+icon change per state via NIM_MODIFY"} |
| 27.4 balloon NIF_INFO | balloon | ok=True · {"api_verdict": true, "screenshot": {"ok": true, "size_bytes": 158411}, "note": "balloons fade — the shell API verdict i |
| 27.5 menu + single-instance raise | menu | ok=True · {"count": 8, "labels": ["فتح NEXUS", "محادثة جديدة", "إيقاف مؤقت", "استئناف", "نقطة حفظ الآن", "حالة النموذج", "الإعدادا |
| 27.6 autostart HKCU | autostart | ok=True · {"command": "\"M:\\NEXUS\\build\\midpoint\\dist\\NEXUS.exe\" --tray", "set": {"registry": {"ok": true, "rc": 0}, "ok": t |
| 27.7 raise via 2nd process | raise | ok=True · {"second_process_rc": 0, "window_state_after": "normal", "event": "NEXUS_UI_RAISE_v27", "screenshot": {"ok": true, "size |
| 27.8 graceful exit | exit | ok=True · {"exit_info": {"settings_saved": true, "checkpoint_files": 4, "tray_delete_ok": true, "raise_handle_closed": true, "utc" |
