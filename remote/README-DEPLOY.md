# NEXUS Remote — دليل النشر (PHASE 28)

## الواجهة على GitHub Pages (28.1)
- الملفات: `remote/web/index.html + app.css + app.js` — ثابتة بالكامل
  (بدون build)، مسارات نسبية، جاهزة للنشر كما هي.
- الـworkflow: `.github/workflows/pages.yml` ينشر `remote/web`
  تلقائياً عند أي push يلمسها.
- في الهاتف: أدخل رابط Pages في صف الاقتران + التوكن.

## البوابة (28.2)
- `NEXUS.exe --remote` → تخدم الواجهة + الـAPI على 127.0.0.1:8899
- التوكن: `M:\NEXUS\remote\token.txt` (يولَّد تلقائياً)
- النفق العام: `cloudflared tunnel --url http://127.0.0.1:8899`

## الـAPI
| المسار | الوصف | توثيق |
|---|---|---|
| GET /api/health | فحص حي (بدون توكن) | 28.0 |
| GET /api/status | حالة النظام | توكن |
| GET /api/tasks | مهام المستودع الحقيقية | توكن |
| POST /api/commands | chat/task/pause/resume/checkpoint | توكن |
| GET /api/commands[/id] | حالة الأوامر | توكن |
| POST /api/files/push | هاتف→جهاز (b64، حتى 8MB) | توكن |
| GET /api/files · /get?name= | outbox→هاتف | توكن |

الأمان: Bearer token على كل شيء عدا health · رفض مسارات
العبور (traversal) مُختبَر كتحقق فعلي في الشهادة.
