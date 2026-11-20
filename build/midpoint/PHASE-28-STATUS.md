# PHASE 28 — Remote Web (حالة حية)

- utc: 2026-11-19T22:36:55Z
- verdict: **PASS** · sections_ok=True (13 قسمًا) · port=8899
- exe: NEXUS.exe · 90844941 B · sha256 ac5becdb7e1f9f24fe8b7ab96c21dcd6…
- الشهادة: proofs\phase28_remote.json
- الواجهة: remote\web\ (index.html + app.css + app.js — جاهزة لـGitHub Pages)
- البوابة مرتبطة: gate_cert_sha256=604e26b360fbc3620f64a4a97e2bcd50…

| # | القسم | البرهان |
|---|---|---|
| 28.0 health | health | ok=True · {"status": 200, "body": {"ok": true, "service": "nexus-remote", "version": "0.25.0"}} |
| 28.2 auth 401×2 | auth | ok=True · {"no_token_status": 401, "wrong_token_status": 401, "note": "401 both — the API is closed without pairing"} |
| 28.2 status | status | ok=True · {"status": 200, "body": {"paused": false, "tasks_count": 1, "model": "…", "port": 8899, "version": "0.25.0"}} |
| 28.3 pause | pause | ok=True · {"command_state": "done", "state_on_disk": {"paused": true, "utc": "2026-11-19T22:36:42Z", "by": "remote"}} |
| 28.3 resume | resume | ok=True · {"command_state": "done", "state_on_disk": {"paused": false, "utc": "2026-11-19T22:36:43Z", "by": "remote"}} |
| 28.3 checkpoint | checkpoint | ok=True · {"command_state": "done", "result": {"checkpoint": "remote_cp_20261120_003645", "count": 4, "dir": "M:\\NEXUS\\checkpoin |
| 28.3 task (M4 real) | task | ok=True · {"command_state": "done", "task_id": "task_4d27a1ac1eb84591b618a519a60d7e53", "rc": 0, "verdict": "PASS", "listed_in_api |
| 28.3 chat honest | chat | ok=True · {"command_state": "done", "model": "offline", "honest": "النموذج المحلي غير مشغّل الآن", "reply_len": 0} |
| 28.4 push sha | files_push | ok=True · {"status": 201, "api_sha": "f2c24b238157fbd6af86", "disk_sha_match": true} |
| 28.4 pull sha | files_pull | ok=True · {"status": 200, "size": 50, "sha_match": true} |
| 28.4 traversal blocked | security | ok=True · {"traversal_pull": 400, "traversal_push": 400, "name_probe_outside_outbox": 404, "note": "traversal rejected 400; outbox |
| 28.1 static served | static | ok=True · {"html_has_title": true, "js_bytes": 7920, "css_bytes": 4219, "html_bytes": 4210} |
| 28.2 CORS | cors | ok=True · {"allow_origin": "*", "options_allow_origin": "*"} |

## التشغيل الحقيقي عن بُعد (للمشغّل)

1. الواجهة: انشر `remote/web` على GitHub Pages (workflow جاهز)
   أو افتحها من الجهاز نفسه عبر البوابة مباشرة.
2. البوابة: `NEXUS.exe --remote` (headless) أو زر الإعدادات في الواجهة.
3. النفق: `cloudflared tunnel --url http://127.0.0.1:8899` → ضع الرابط
   والتوكن (`remote\token.txt`) في هاتفك (صف الاقتران).
