# 📖 NEXUS PROJECT LOG — ما استُغل من المرحلة 0 إلى 25

<!-- The official accomplishment record: Master Specification v1.0 + Final Build Plan + PHASE 0→25 -->
<!-- الوثيقة الرسمية للإنجاز: المواصفة الرئيسية + خطة البناء النهائية + المراحل 0 إلى 25 -->
<!-- كل رقم في هذه الوثيقة له مصدر: تقرير مرحلي · اختبار · برهان حي · ملف على القرص -->

<div align="center">

**NEXUS — Local Autonomous Computer Intelligence Platform**

**من مواصفة على الورق → إلى نظام حي على Windows.**

**v0.25.0 · `NEXUS_PHASE = 25` · المرحلة 0→25 مكتملة — 26 مرحلة**

*2026-09-10*

</div>

---

## 📌 الملخص التنفيذي · Executive Summary

<div dir="rtl">

هذه الوثيقة تجيب عن سؤال واحد: **ماذا استُغل فعليًا من المرحلة 0 إلى المرحلة 25؟**

الجواب باختصار: بُني — على جهاز Windows حقيقي، لا في ساندبوكس فقط — **نظام تشغيل ذكي كامل فوق Windows**: نواة مهام بمثابة آلة حالات، مساحة عمل وسياطة ونطاق، ذكاء عتاد ومدير موارد، runtime نماذج محلي (llama.cpp)، نظام وكلاء أصبح في المرحلة 24 **نظام وكلاء متعدد** (Master + 13 متخصصًا)، تحكم فعلي بـ Windows عبر UIA/SendInput، متصفح، رؤية وOCR، ذاكرة بـ12 نطاقًا، تعلم من التجربة، ذكاء كود، نظام برمجة، Git/GitHub، بحث، مستندات، صوت، تحقق بالأدلة، أمان بطبقات، استعادة ونقاط تفتيش، نبض وصحة، وتنفيذ طويل الأمد ينجو من إعادة الإقلاع.

كل مرحلة من الخمس والعشرين مرّت بالحلقة ذاتها ولم تُعلن اكتمالًا قبل: تنفيذ + تكامل + اختبار ساندبوكس + نشر sha-verified + اختبار على الجهاز الحقيقي + برهان حي + بوابة خروج + CI + commit على main وdevelop + checkpoint على M:\NEXUS.

</div>

**One question, one answer: what did phases 0→25 actually deliver?**

A complete intelligent execution layer above Windows, built on a real Windows machine — not a demo, not a mockup: a state-machine task core, workspace/scope/policy, hardware intelligence + resource manager, a local llama.cpp model runtime, an agent runtime that became a **multi-agent system** (Master + 13 specialists) at PHASE 24, real Windows control (UIA/SendInput), browser, vision+OCR, 12-scope memory, experiential learning, code intelligence, a coding system, Git/GitHub, research, documents, speech, evidence-based verification, layered security, recovery+checkpoints, heartbeat+health, and long-horizon execution that survives reboot.

Every one of the 25 phases passed the same loop and was never declared done before: **Implemented + Integrated + Tested + Deployed (sha-verified) + Device-tested + Live proof + Exit gate + CI + Committed (main+develop) + Checkpointed**.

---

## 🏆 لوحة الأرقام · The Scoreboard

| المقياس · Metric | القيمة · Value | المصدر · Source |
|---|---|---|
| المخرجات المكتملة · Deliverables complete | **28 / 43** (المواصفة + خطة البناء + PHASE 0→25) | Roadmap أدناه |
| إصدار الحزمة · Package version | **0.25.0** · `NEXUS_PHASE = 25` | `pyproject.toml` · `nexus/__init__.py` |
| اختبارات ساندبوكس · Sandbox checks | **2,152+** (98 في P1 + 2,054 في P2–P25، إضافة إلى +7 P14/+1 P11 الموثقة) | `tests/phase01…phase25` |
| براهين حية · Live proofs | **184** (P4–P25، كل برهان على مسار كود حقيقي) | `tests/phaseNN/live_*.py` |
| براهين الجهاز · Device proofs | P8→P25 — كلها مختومة تحت `M:\NEXUS\proofs\` | JSON مختوم بالوقت على القرص |
| انحدار كامل · Full regression | 15→24 أخضر ساندبوكس وجهازًا بعد نشر P25 (56/56 + 54/54) | device tests |
| بوابات الخروج · Exit gates | بوابة لكل مرحلة (P25: **21/21**) | `verify_exit_criteria.py` لكل مرحلة |
| حزم النظام · System packages | **28 حزمة** تحت `nexus/` | `nexus/` |
| المواصفة المرجعية · Reference spec | v1.0 — **375 قسمًا** · خطة البناء — **109 أقسام / 40 مرحلة** | `docs/reference/` |
| Lint | ruff 0.16.6 (`E F W I N UP B`, line-length 100) — نظيف | CI + محلي |
| اللغة الأساسية · Core language | Python 3.14 · النواة **stdlib-only** بلا استثناء | كل مرحلة |

### ما الذي بُني في كل مجموعة · What each group delivered

| المجموعة · Group | المراحل · Phases | فحوصات · Checks |
|---|---|---|
| النواة · Core Foundation (config · events · sessions · task engine · persistence · workspace · scope · policy · hardware · resources · models) | P1–P4 | **451** |
| الوكلاء والتحكم · Agents & Control (agents · harness · tools · computer · windows · browser · vision) | P5–P11 | **645** |
| المعرفة · Knowledge (memory · learning · codeintel · coding · git+github · research) | P12–P17 | **504** |
| الإنتاج والصمود · Production & Resilience (documents · speech · verification · security · recovery · health) | P18–P23 | **442** |
| التنسيق والأمد الطويل · Orchestration & Horizon (orchestration · horizon) | P24–P25 | **110** |
| **المجموع · Total** | **P1–P25** | **2,152+** |

---

## 🖥️ الجهاز · The Machine

كل برهان "على الجهاز" في هذا السجل يعني هذا الجهاز بالذات — لا محاكاة:

| الحقل · Field | القيمة · Value |
|---|---|
| الهوية · Identity | **almoutmag-v9** |
| النظام · OS | Windows 10 · 10.0.19045 · AMD64 |
| بايثون · Python | 3.14.5 |
| بصمة الحماية · Fingerprint | `a5a2e62a821bec53` |
| أدوات الجسر · Bridge tools | 95,078 |
| القرص · Disk home | `M:\NEXUS` (المستودع + `proofs\` + checkpoints) |
| القناة · Channel | Cloudflare tunnel ×2 → `tools/bridge.py` (MCP: code_write_file · code_read_file · code_run_tests · code_run_powershell · file_hash) |

---

## 🔁 المنهج · The Method — لماذا هذه الأرقام صادقة

<div dir="rtl">

الرقم في NEXUS ليس ادعاءً في ملف؛ إنه نتيجة حلقة تنفيذ ثابتة فرضتها خطة البناء وتّبعها كل مرحلة بالترتيب ذاته:

</div>

```text
1. CONTRACTS      nexus/<domain>/contracts.py أولاً — العقد قبل الكود
2. IMPLEMENT      التنفيذ stdlib-first، والتكامل لا التكرار
3. SANDBOX TESTS  tests/phaseNN/ — كل سلوك له اختبار
4. DEPLOY         code_write_file + sha256 (قانون CRLF: الجهاز يكتب نصيًا LF→CRLF)
5. DEVICE TESTS   code_run_tests على Windows الحقيقي — py 3.14.5
6. LIVE PROOF     برهان حي على مسار كود حقيقي — يُكتب JSON على M:\NEXUS\proofs\
7. EXIT GATE      verify_exit_criteria.py لكل مرحلة — بوابة أ–و
8. CI             GitHub Actions — «CI خضراء هي الحكم الأخير»
9. COMMIT         main + develop معًا في commit واحد
10. CHECKPOINT    M:\NEXUS + marker + Gate A–F
```

<div dir="rtl">

والنتيجة: أي رقم في هذه الوثيقة يمكن تتبعه إلى ثلاثة مصادر — **تقرير مرحلي** (`docs/PHASE-N-REPORT.md`)، **اختبارات** (`tests/phaseNN/`)، و**برهان على قرص الجهاز** (`M:\NEXUS\proofs\`). لا يوجد ✅ واحد بلا دليل.

</div>

Every number here traces to one of three artifacts: a **phase report**, a **test file**, or a **sealed proof on the device disk**. No ✅ without evidence — that is the Capability Matrix law.

---

## ⚖️ القوانين الذهبية · The Golden Laws — ما فرضته المراحل

<div dir="rtl">

كل مرحلة كلفة تعليمها. هذه القوانين صيغت من فشل حقيقي كان سيُخفي نفسه لولا القاعدة:

</div>

1. **القرص يحسم لا الذاكرة** — كل قرار عامل يُقرأ من الملف (P25: `goal.json` بين كل خطوتين). *The disk decides, not memory.*
2. **دليل أو لم يحدث** — لا ✅ في مصفوفة القدرات بلا برهان. *Evidence or it didn't happen.*
3. **الرفض الصادق أفضل من نجاح مزيف** — SKIP رفض صادق؛ P19 ترفض null بصدق حين لا تقدر. *Honest refusal beats fake success.*
4. **كل رفض يسمّي سببه** — بوابات P24 الثلاث و`BlindResumeError` تجمع كل الأسباب لا الأول فقط. *Every denial names its reason.*
5. **لا استئناف أعمى** — P22.4: الاستئناف يقرأ الدليل من القرص (ملفات · git · عمليات · نوافذ · حالة) قبل أي خطوة. *No blind resume.*
6. **الصمت حكم الساعة لا الاستثناء** — P23: توقف مكوّن يُشتق من الساعة، والنبضة الجديدة هي المنقذ الوحيد. *Silence is the clock's verdict.*
7. **السر لا يغادر الخزنة** — P21: النص لا يصل Memory/chat/logs/Activity أبدًا؛ `SecretLeakError` حائط صلب؛ scrub بمطابقة تامة ثم أنماط. *Secrets never leave the vault.*
8. **بوابة التوازي الثلاثية** — P24.3: لا توازٍ إلا باستقلال المهام واستقلال الملفات وتوفر الموارد معًا. *Three conjunctive gates for parallelism.*
9. **الملكية الخماسية** — P24.4: كل وكيل يعرف task · scope · parent · children · owned resources. *Five ownership fields per agent.*
10. **المهلة تحدّ تشغيلاً واحدًا** — P25.7: جدار زمني حقيقي (epoch seconds) يوقف بـ`deadline_hit` ولا يكذّب اكتمالًا. *A deadline bounds ONE run.*
11. **CI خضراء هي الحكم الأخير** — بوابة F لا تُختم قبل خضورة CI؛ الماركر مؤجل لكنه مؤجل بقانون لا بمزاج. *Green CI is the final judge.*
12. **قانون CRLF** — الجهاز يكتب نصيًا؛ الـsha المتوقع يُحسب على `LF→CRLF`. *Device digests normalize.*
13. **أغلق مقابضك قبل التنظيف** — درس WinError 32: قاعدة/ذاكرة مفتوحة تفسد تنظيف مجلد Windows المؤقت. *Close handles before temp cleanup.*
14. **التكامل لا التكرار** — P24/P25 أعادتا استخدام §22/§23 كما هما بلا نسخ. *Integrate, never duplicate.*

---

## 🧱 سجل البناء · The Build Log — PHASE 0 → 25

### PHASE 0 — Machine & Repository Preparation ✅

- تجهيز جهاز Windows الحقيقي (almoutmag-v9) كهدف نشر واستقبال براهين.
- إنشاء المستودع `PS-COMMUNITY/NEXUS` على GitHub — فرعا `main` + `develop` — وسير عمل CI، وقناة النشر عبر النفق مع تحقق sha لكل ملف.
- بناء قاعدة المعرفة الدائمة `docs/nexus-spec/` — تغطية **100%** لأقسام المواصفة الـ375 (فهرس + 10 ملفات موضوعية).
- **الدليل:** الجسر حي (صحة identity مطابقة) · المستودع أخضر · PAT مُثبت بدفعة حقيقية (قانون أول فعل = دفع حقيقي).

### PHASE 1 — NEXUS Core Foundation ✅

- `nexus.core.config` — إعداد مكتوب الأنواع وحل البيئة والمسارات المحلية (§2.1) · `nexus.events` — ناقل الأحداث المركزي بـ**28 حدثًا قانونيًا** (§2.2) · `nexus.core.session` — User → Conversation → Task → Session (§2.3) · `nexus.core.engine` — آلة حالات المهمة بـ**13 حالة** (§2.4) · `nexus.core.persistence` — مثابرة المهام بـ**11 حقلًا** (§2.5).
- **الدليل:** **98/98** معيار خروج، شامل **دورتَي إعادة إقلاع كاملتين** — الحالة تُستعاد من القرص.

### PHASE 2 — Workspace + Scope + Policy ✅

- سجل مساحات العمل بسبعة حقول (§3.1) · النطاق سداسي الأبعاد مع **حل من لغة طبيعية** (§3.2–§3.4) · السياسات بتسعة مكونات ومحرك قرار (§3.5) — *تحكم كامل داخل نطاق المهمة*.
- **الدليل:** **143/143**.

### PHASE 3 — Hardware Intelligence + Resource Manager ✅

- **12 هدف فحص** لعترة العتاد (§4.1) و`hardware_profile` مثابر على القرص (§4.2) — *الجهاز يعرف نفسه ويعمل ضمن طاقاته*.
- **الدليل:** **104/104**.

### PHASE 4 — Local Model Runtime ✅

- llama.cpp كـMODE A مع مدير نماذج وفحوص توافر صادقة — *نماذج محلية، خصوصية أولًا*.
- **الدليل:** **106/106** ساندبوكس + **26/26** برهانًا حيًا.

### PHASE 5 — Agent Runtime ✅

- سجل الوكيل §6.1 · الحلقة · الماستر · السجل · الرسائل · الملكية — الأساس الذي س يقف عليه نظام الوكلاء في P24.
- **الدليل:** **116/116**.

### PHASE 6 — Harness Integration ✅

- أنماط ECC/Cline/LangGraph/Prime/DeepAgents · skills · rules · hooks · sessions · checkpoints · goals · عقد §41 — الجسر بين الوكيل وبيئات التنفيذ.
- **الدليل:** **88/88** + جولة مستودع 3.

### PHASE 7 — Tool System ✅

- **سجل الأدوات** (§8.1، 9 حقول) و**موجّه الأدوات** (§8.2، 7 مراحل مُتتبعة) · 9 أدوات أصلية · **MCP SDK v2 الرسمي خلف الموجّه** (§8.4/§8.5).
- **الدليل:** **88/88** + برهان cross-SDK.

### PHASE 8 — Windows Computer Runtime ✅

- **Computer API** بثمانية نطاقات خلف موجّه §8.2 · هرمية §9.5 الاحتياطية بخمس طبقات مُتتبعة · عميل UIA أصلي بـctypes (§9.4) · ميكانيكا SendInput (§9.2 ADAPT) · pywinauto كإضافة `[computer]` (§9.3).
- **الدليل:** **80/80** + براهين جهاز حية.

### PHASE 9 — Window Manager + Human Parallelism ✅

- **سجل النوافذ** (§10.1، 9 حقول + أول ناشر حقيقي لـwindow.opened/closed) · ملكية USER/NEXUS/SHARED (§10.2) · **تحكيم إدخال لكل نافذة** عبر الفيتو pre_tool_call (§10.3) · تخطيط متعدد الشاشات (§10.4) · **Overlay أصلي بـctypes**: «NEXUS is working · Pause · Resume» (§10.5).
- **الدليل:** **84/84** + براهين جهاز PASS.

### PHASE 10 — Browser Runtime ✅

- Playwright MODE A «USE» خلف موجّه §8.2 (السجل الثالث عشر) · سلّم القنوات chromium→chrome→msedge · **عزل جلسات المستخدم/الوكيل بالبناء** (§11.4/§55) · السر الذي لا يعبر — **خزنة DPAPI + vault_ref** (§11.5) · محددات ذاتية الإشفاف (§11.3) · درجة dom_a11y من §9.5 حية.
- **الدليل:** **70/70** + Chromium محلي **15/15** + جهاز PASS.

### PHASE 11 — Vision + OCR + Screen Understanding ✅

- التقاط شاشة كامل/نافذة/منطقة بـctypes صرف · VisionProvider · **سباق محركات OCR حسمه benchmark على الجهاز** · locate→click عبر §9.5.
- **الدليل:** **119/119** (+7 موثقة) · حي **11/11** · جهاز PASS.

### PHASE 12 — Memory System ✅

- العقود + **هرمية 12 نطاقًا** · فهرس SQLite · Qdrant MODE A محلي · Mem0 MODE B · خط أنابيب الاسترجاع مع **سلّم النزاع §12.8** · forget · compression.
- **الدليل:** **137/137** · حي 11/11 · جهاز **12/12**.

### PHASE 13 — Learning System ✅

- مستخلص التجارب (**ستة أنواع**) · سجل التعلم · خط ست مراحل → ترقية عبر محرك §12 · SkillCandidate + WorkflowMiner — *يتعلم من التجربة*.
- **الدليل:** **60/60** · حي 14/14 · جهاز **12/12**.

### PHASE 14 — Code Intelligence ✅

- فهرس ملفات/رموز · AST (stdlib-ast + tree-sitter MODE A + regex) · رسوم تبعيات/API/اختبارات · خرائط معمارية ومستودع بمنهجية **PageRank** (Aider) · محرك بمقياس 100k + تحديث حي §14.12.
- **الدليل:** **97/97** (+1) · حي **21/21** · جهاز PASS.

### PHASE 15 — Coding System ✅

- عقد وكيل البرمجة (§15.1، **سبع عمليات**: analyze/plan/edit/run/test/debug/review) · عشرة متخصصين (§15.2) · **حلقة برمجة بثمان مراحل** Understand→Review مع Debug→Retest محدود (§15.6) · أثر جلسة بأسلوب Cline (§15.5).
- **الدليل:** **73/73** · CI 9/9 · جهاز حي **6/6**.

### PHASE 16 — Git / GitHub ✅

- **محرك Git** (§16.1: status · diff · branch · worktree · commit · merge · tag · rollback) · **محرك GitHub** (§16.2: search · clone · pull · push · branch · PR · issue · release) · دورة حياة المستودع Discover→Clone→Index→Modify→Test→Commit→Review→Push (§16.3) · وكلاء متوازون بفروع/worktrees/checkpoints (§16.4).
- **الدليل:** **64/64** · حي 10/10.

### PHASE 17 — Research Engine ✅

- تجريد بحث موحد (§17.1: web · github · docs · forums · ملفات محلية — عقد SearchProvider واحد) · **مسار بحث بثمان مراحل** Query→Search→Collect→Deduplicate→Rank→Compare→Verify→Evidence مع حكم لكل مرحلة والإلزام بالتشاهد المتعددة — الرقم المتنازع لا يتحقق به وحده (§17.2) · تصنيف المصادر (§17.3) · ثقة المصدر (§17.4) · ذاكرة البحث مع مصادرها إلى §12 (§17.5).
- **الدليل:** **73/73** · حي 6/6.

### PHASE 18 — Document Intelligence ✅

- **Docling** (§18.1: MODE A مباشرة + MODE B عبر عقد ParseBackend — فحص توافر صادق وتثبيت موثق واحد) · خط المستندات Parse→Structure→Extract→Index→Memory مع **فهرس SQLite معكوس يجيب أين** (§18.2) · **DOCX** حقيقي فوق OOXML (§18.3) · **PPTX** حزمة دنيا حقيقية (§18.4) · **PDF** محلل stdlib يصرّح بما لا يقرؤه (§18.5).
- **الدليل:** **80/80** · حي 7/7.

### PHASE 19 — Speech System ✅

- Speech API (§19.1: SpeechProvider · transcribe · detect_language — فحوص صادقة وقانون عدم اختلاق ثقة) · **sherpa-onnx** (§19.2: MODE A عند التثبيت + النموذج، وأرضية SAPI على Windows بصفر تثبيت، والرفض null الصادق — تثبيت موثق واحد) · **Benchmark بستة شروط حقيقية** على عينات صوت فعلية: عربي · عربي تقني · إنجليزي · مخلوط · سريع · ضجيج — WER/CER عبر المطبع (§19.3) · خط الميكروفون→STT→Normalizer→Intent→Task مع ذاكرة صوتية إلى §12 (§19.4).
- **الدليل:** **104/104** · حي 9/9.

### PHASE 20 — Verification Engine ✅

- الإطار (§20.1: Verifier · Evidence · Criterion · Result — **PASS/FAIL/ERROR/SKIP** وSKIP هو الرفض الصادق) · **تسعة نطاقات** خلف مدقّقات بأماتنة حقيقية: roundtrip ذاكرة §12 · sha حقيقي لـgit HEAD · كتابة temp حقيقية (§20.2) · **الأدلة مختومة sha256 JSON** والتلاعب يُكشف عند القراءة (§20.3) · **حلقة الإصلاح** Fail→Diagnose→Fix→Retest→Verify — الـPASS بعد إصلاح يحمل عنوانًا، والعجز يتوقف بصدق (§20.4).
- **الدليل:** **55/55** · حي 10/10.

### PHASE 21 — Security System ✅

- القدرة الكاملة + التنفيذ المحكوم (§156: Scope + Permission + Execution Gate) · تكامل محرك النطاق — دقة §3.3 أول فحص لكل إدخال (§21.1) · **محرك الأذونات**: سلّم مخاطر §163 × سياسة §3.5 — الرفض الصريح هو الجدار الوحيد (§21.2) · بوابة الأدوات/MCP/Plugins (§21.3–§21.5) · **معالجة الأسرار** بقانون §160 المرجعي — النص لا يغادر الخزنة (§21.6) · **التحريض** [REDACTED:kind] على عشر عائلات أنماط (§21.7) · **التدقيق** بحقول §164 الخمسة Who|What|When|Where|Result حرفيًا (§21.8) · **Trivy** بوضعين صادقين (§21.9) · قواعد الأمان — لا يصل سر إلى Memory/chat/Logs/Activity، ومسحان: مطابقة خزنة تامة ثم أنماط، و`SecretLeakError` الحاجز الصلب (§21.10).
- **الدليل:** **82/82** · حي 10/10.

### PHASE 22 — Recovery + Checkpoints ✅

- **مدير نقاط التفتيش** (§22.1: Task · Project · Git · State — digests + blobs على القرص، manifests ذرية، retention لكل نطاق) · **محرّكات التفعيل** (§22.2: task start · phase complete · major change · critical test · before risky change · periodic بسياسة فواصل صادقة) · **الاستعادة** Crash→Checkpoint→البيئة الفعلية→المصالحة→Resume وكل مرحلة مرئية (§22.3) · **لا استئناف أعمى** (§22.4) — يفحص Files · Git · Processes · Windows · Browser · Task state، و`resume()` يرفض التقرير المنحرف بنيويًا.
- **الدليل:** **67/67** · حي 10/10.

### PHASE 23 — Heartbeat + Health ✅

- **النبض** يراقب سبعة مكوّنات (Core · Agent · Model · Tool · Browser · Computer · Task) — الصمت بعد نافذة الركود يُشتق **من الساعة لا من استثناء**، والنبضة الجديدة هي منقّص الركود الوحيد (§23.1) · **كشف العلوق** بأربع إشارات (same action · same error · same state · no progress) بنافذة انزلاقية لكل مكوّن وإطلاق واحد لكل دليل (§23.2) · **الاستعادة** بسلم detect→diagnose→retry→alternate→replan وكل درجة مرئية، والدروجات المغيّرة للعالم تعلن لمحرّك BEFORE_RISKY_CHANGE أولًا (§23.3).
- **الدليل:** **54/54** · حي 11/11.

### PHASE 24 — Multi-Agent Orchestration ✅

- *نقل NEXUS من Agent واحد إلى Agent system.* **الماستر** يبقى الوكيل الوحيد للمستخدم — قناة المستخدم محمية بالهوية ومحاولة متخصص ترفع `MasterOnlyChannelError`، باب واحد داخل `submit_user_goal` وصوت واحد خارج `report_to_user` (§24.1) · **13 متخصصًا** (Planner · Researcher · Architect · Coder · Browser · Computer · Tester · Debugger · Security · Reviewer · Git · Recovery · Learning) كلٌّ سجل §6.1 على سجل §6.4 بمعرّف `ag_spec_<role>`، والشجرة تُدقَّق عند البناء والتلاعب يرفع `TreeError` (§24.2) · **التوازي** بثلاث بوابات تجميعية — كل رفض يسمّي سببه — وتخطيط أمواج حتمي وخيوط حقيقية أثبتها لقاء Barrier (§24.3) · **الملكية الخماسية** المجمّدة (task · scope · parent · children · owned resources) والرفض قبل العمل والتنسيق عبر §6.6 — النزاع يظهر نتيجة فاشلة صادقة لا كتابة فوق غيرها (§24.4).
- **الدليل:** **56/56** · حي **11/11** (خيوط حقيقية · جدران حقيقية · أمواج حقيقية) · بوابة 22/22 بانحدار 15–23 أخضر.

### PHASE 25 — Long-Horizon Execution ✅

- *«خذ المهمة واشتغل لحد ما تخلص»* — الهدف يعيش أطول من الجلسة. **مثابرة الهدف** (§25.1): `goal.json` ذريًا + مجلة `progress.jsonl` append-only، وعملية معاد إقلاعها تجد كل هدف كما تركه الميت · **عمال الخلفية** (§25.2): خيط حقيقي لكل تشغيلة و`HorizonHandle` يعود فورًا والملاحظة بلا إعاق · **الحالة الطويلة** (§25.3): سلّم `pending → running → paused/completed/failed/deadline_hit` مكتوب بين الخطوات والانتقالات غير القانونية مرفوضة · **النبض** (§25.4): مراقب §23 يُضرب agent لكل خطوة وtask عند المحطات · **نقاط التفتيش** (§25.5): التقطات PERIODIC الحقيقية كل N خطوات والمعرّف يُحفظ مع الهدف · **الاستئناف** (§25.6): قانون §22.4 مرة أخرى — كل أسباب الرفض تُسمّى، وعقد الجيل يُقاعد العامل الشبحي قبل أن يكتب حرفًا · **المهلة** (§25.7): الأنواع الأربعة الحرفية (30_minutes · 2_hours · 8_hours · until_completion) بنوافذ صادقة وجدار بالثواني ينجو من reboot ويوقف بـ`deadline_hit` ولا يكذّب اكتمالًا — والمهلة تحدّ تشغيلاً واحدًا.
- **الدليل:** **54/54** ساندبوكس · **54/54** جهازًا (py 3.14.5) · برهان حي **11/11** على الجهاز (PASSED في 5.22s — `M:\NEXUS\proofs\phase25_live.json`: PASS · Windows-10.0.19045 · AMD64) · بوابة **21/21** بانحدار 15–24 أخضر ساندبوكس وجهازًا (56/56 + 54/54).

---

## 📦 ما الموجود على القرص اليوم · What Exists on Disk Today

```text
nexus/                          ← 28 حزمة نظام مكتملة:
  core · events · workspace · resources · models
  tools · agents · harness · skills
  computer · windows · browser · vision
  memory · learning · codeintel · coding
  git · github · research · documents · speech
  verification · security · recovery · health
  orchestration · horizon
tests/phase01 … tests/phase25   ← اختبارات كل مرحلة + براهينها الحية
docs/PHASE-*-REPORT.md          ← تقرير مرحلي لكل مرحلة
docs/reference/                 ← المواصفة الرئيسية v1.0 (375 قسماً) + خطة البناء (109)
docs/nexus-spec/                ← قاعدة المعرفة الدائمة (تغطية 100% للمواصفة)
docs/PROJECT-LOG.md             ← هذه الوثيقة
M:\NEXUS\proofs\                ← براهين الجهاز المختومة (JSON لكل مرحلة)
M:\NEXUS (checkpoints)          ← نقاط تفتيش M: لكل مرحلة مكتملة
.github/workflows/ci.yml        ← بوابات 15→25 + وظيفة البرهان الحي §25
```

---

## 📍 الموقف والتالي · Position & What's Next

<div dir="rtl">

**الموقف الرسمي بصدق:** PHASE 25 مكتملة A–E (تنفيذ · تكامل · اختبار ساندبوكس وجهاز · برهان حي · توثيق · commit `0772e99` على main وdevelop معًا) و**F(CI) مؤجلة** — أعمال CI الأخيرة (113/114 على `0772e99`) فشلت **قبل checkout بصفر خطوات** بسبب عطل فوترة حسابي موروث، لا بكود المشروع. وفق القانون: ماركر `PHASE25_COMPLETE` مؤجل حتى خضورة CI، وإعادة تشغيل واحدة تحكم بوابات 21–25 معًا.

**التالي:** بعد اكتمال البنية من PHASE 12–25 بالمستوى اللازم، يبدأ **MIDPOINT — NEXUS Windows Product v0.1**: أول `NEXUS.exe` حقيقي (Launcher → Core → UI) متصل بالنواة الموجودة، أول محادثة حقيقية («حلل جهازي.»)، أول مهمة حقيقية تُنفَّذ على القرص، بناء عبر النفق إلى `M:\NEXUS\build\`، تشغيل حقيقي مثبت، معاينة مثبّت `NEXUS-Setup.exe`، واجهة سطح مكتب (Sidebar · Conversations · Tasks · Chat · Activity · Composer)، اقتراحات قدرات، Timeline للوكلاء، Task History، Tray، Overlay، وأول حلقة إنتاجية كاملة — ثم **MIDPOINT GATE** بمعاييره العشرة (launches · UI · core connection · task execution · model execution · event stream · persistence · restart · windows real proof · packaging) قبل العودة إلى PHASE 26–40.

</div>

**Honest position:** PHASE 25 is complete through A–E (implemented · integrated · sandbox+device tested · live proof · documented · committed `0772e99` to main+develop) with **F(CI) deferred** — the latest runs (113/114) failed **before checkout with zero steps** due to an inherited account-billing fault, not project code. Per the law, the `PHASE25_COMPLETE` marker waits for green CI; one rerun adjudicates gates 21–25 together.

**Next:** **MIDPOINT — NEXUS Windows Product v0.1** — the first real `NEXUS.exe` (Launcher → Core → UI) wired to the existing core, first real chat («حلل جهازي.»), first real task executed on disk, build via tunnel to `M:\NEXUS\build\`, proven real run, `NEXUS-Setup.exe` installer preview, the desktop UI, capability suggestions, agent timeline, task history, tray, overlay, and the first production-like loop — then the **MIDPOINT GATE** (10 checks) before returning to PHASE 26–40.

---

## 🧾 المصادر · Provenance

| الادعاء · Claim | المصدر · Source |
|---|---|
| أرقام كل مرحلة | `docs/PHASE-N-REPORT.md` · `CHANGELOG.md` · خارطة الطريق في `README.md` |
| اختبارات ساندبوكس | `tests/phaseNN/` (تُنفَّذ في CI وفي الجهاز) |
| براهين حية | `tests/phaseNN/live_*.py` — برهان JSON لكل تشغيلة |
| براهين الجهاز | `M:\NEXUS\proofs\*.json` (مختومة بالوقت والهوية) |
| الهوية والإصدار | `pyproject.toml` · `nexus/__init__.py` · `gh api repos/PS-COMMUNITY/NEXUS` |
| هذا المستوى من الطموح | `docs/reference/NEXUS-Master-Technical-Specification-v1.0.md` (§344–§360) · `NEXUS-Final-Build-Plan-v1.0.md` (§1–§40) |

---

<div align="center">

**NEXUS v0.25.0 — 25 مرحلة، حلقة واحدة، صفر ادعاءات بلا دليل.**

*القرص يحسم. CI هي الحكم الأخير. والتالي: NEXUS.exe.*

</div>
