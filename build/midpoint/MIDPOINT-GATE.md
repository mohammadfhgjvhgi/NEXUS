# MIDPOINT GATE — 10 checks before PHASE 26
# بوابة منتصف الطريق — عشرة معايير قبل PHASE 26 (README/PROJECT-LOG contract)

Target: **NEXUS Windows Product v0.1** — أول NEXUS.exe حقيقي (Launcher → Core → UI)
متصل بالنواة الموجودة (v0.25.0, 28 حزمة). القرص يحسم — كل فحص له برهان على القرص.

| # | الفحص · Check | البرهان · Evidence | الحالة |
|---|---|---|---|
| 1 | Launcher boot self-check PASS — كل حزم النواة الـ28+ تستورد | `proofs\midpoint_boot.json` (verdict=PASS) | ✅ **منفذ** — 37/37 ok · 4.59s |
| 2 | NEXUS.exe يُبنى فعلاً (PyInstaller onefile) | `build\midpoint\dist\NEXUS.exe` + sha256 | ✅ **منفذ** — v5 النهائي: 87,587,935 B · sha256 c9e386bb8adf6c55... · 256s · `proofs\midpoint_build.json` |
| 3 | أول تشغيل حقيقي للـexe: `NEXUS.exe --check` PASS | إخراج الفحص + شهادة إقلاع محدثة | ✅ **منفذ** — rc=0 · الشهادة كتبها الـexe المجمد نفسه (37/37 ok) — يُعاد التأكيد مع كل بناء |
| 4 | أول محادثة حقيقية محلية (Ollama MODE A2) | سجل `--say`/`--chat` (prompt→content) | ✅ **منفذ** — `NEXUS.exe --say "مرحباً يا NEXUS..."` → رد عربي نظيف (89.6s) · qwen3:0.6b · `proofs\midpoint_chat.json` verdict=PASS · has_FFFD=false |
| 5 | أول مهمة حقيقية عبر محرك المهام (Task State Machine) | مهمة `task_b9b28770d20f44e4bffdba9376c604e1` COMPLETED + سجل محفوظ | ✅ **منفذ** — NEXUS.exe --task · filesystem عبر Router · persistence roundtrip · `proofs\midpoint_task.json` |
| 6 | UI سطح مكتب أولي (نافذة محادثة) | نافذة حقيقية + قائمة مهام حقيقية + لقطة | ✅ **منفذ** — tkinter · sidebar tasks من المستودع · **بطاقات القدرات M10 (7 بطاقات) + بطاقة المشروع** · لقطة GDI `proofs\midpoint_ui.png` · `proofs\midpoint_ui.json` |
| 7 | أيقونة صينية Tray + قائمة | لقطة tray | ✅ **منفذ** — Shell_NotifyIconW NIM_ADD/MODIFY/DELETE = TRUE · قائمة 4 بنود مبنية · لقطة سطح مكتب `proofs\midpoint_tray.png` (الأيقونة قد تكون في overflow) |
| 8 | Overlay فوق التطبيقات | لقطة overlay | ✅ **منفذ** — Toplevel topmost+alpha · Pause/Resume يعملان فعلاً · لقطة `proofs\midpoint_overlay.png` · `proofs\midpoint_overlay.json` |
| 9 | معاينة مثبّت (installer preview) | installer skeleton | ✅ **منفذ** — NEXUS-Setup.exe ثبّت المنتج في %LOCALAPPDATA%\Programs\NEXUS + مفتاح إزالة في السجل + قائمة ابدأ + شغّل المثبَّت واختباره (--check PASS) · `proofs\midpoint_install.json` |
| 10 | شهادة MIDPOINT موقعة sha256 تختصر 1–9 | `proofs\midpoint_gate.json` | ✅ **منفذ** — سلسلة sha256 لكل أدلة 1–9 · البصمة 604e26b360fbc3620f64a4a9… · sealed_by worker_task910 |

## القواعد الثابتة · Standing laws
- **stdlib-only** في النواة والـLauncher — الثقيل خلف Adapters (MODE A–F موثقة).
- كل فحص فاشل يُكتب **بصدق** — لا بند أخضر بلا برهان على القرص.
- البناء **على الجهاز** (tunnel → `M:\NEXUS\build\midpoint\`) — لا بناء في السحابة.
- الخطة (Final Build Plan) مرجع ماذا-وكيف؛ أي تعارض = Bug أو مراجعة موثقة أولًا.

## القوانين الهندسية المثبتة اليوم (2026-09-13)
- **frozen-aware**: onefile يفك في مجلد مؤقت و`__file__` يكذب — الـlauncher يحدد جذر M:\NEXUS بالمشيأ للأعلى من `sys.executable` حتى `nexus/__init__.py`.
- **37 hiddenimports**: جذر الحزمة lazy — بدون تثبيت كل الوحدات لكان الـexe ناقصًا بصمت.
- **local-first لا يبركسي الlocalhost**: `_local_opener()` = ProxyHandler({}).
- **عتاد هذا الجهاز**: i7-3770 (Ivy Bridge — AVX بلا AVX2) → كل باكندات LM Studio llama.cpp تموت فورًا (0xC000007D)؛ **Ollama يعمل** (.MODE A2)؛ GTX 750 Ti 4GB حية.
- **qwen3 نموذج تفكير**: المحادثات ترسل `think:false` + `num_predict` (سلاسل التفكير الطويلة قتلت المهلات عند ~3 tok/s).
- **الترميز**: `--say` يمرر البرومبت عبر argv (CreateProcessW موحِّد) والمنتج يعيد تشكيل stdio إلى UTF-8 — لا stdin ولا codepage لوكيدي.
- **العمال المنفصلون**: كل عملية بناء/محادثة تعيش بعد موت خدمة MCP — القلوب النابضة والشهادات على القرص دائمًا.

## الخطوة التالية بعد البوابة
#5 — أول مهمة حقيقية عبر محرك المهام، ثم PHASE 26 — Desktop UI Production.

## MIDPOINT-10 — بطاقات القدرات + بطاقة المشروع
- بطاقات New Chat السبع: Full Stack · Android · Research · Coding · Automation · Computer · Documents — **ليست Modes مغلقة**: كل بطاقة تبذر برومبت بداية في الـcomposer (فحص وظيفي حقيقي: بطاقة Coding بذّرت الـcomposer — `cap_seed_check=ok`).
- بطاقة المشروع شريط هوية داخل الواجهة + وثيقة `build\midpoint\PROJECT-CARD.md` (نسخة في proofs).
- برهان: `proofs\midpoint_cards.json` (verdict=PASS) + لقطة محدثة `proofs\midpoint_ui.png`.
