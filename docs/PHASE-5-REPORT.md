# PHASE 5 — Agent Runtime · Completion Report

**الحالة**: Implemented + Integrated + Tested + Verified + Documented — **116/116**
**الالتزام**: Plan §6.1–§6.6 حرفيًا · stdlib only · صفر أسماء أحداث جديدة (سجل §2.2 = 28 ملزمًا) · §0.5 محفوظ (Master Agent + Agent Registry ملك NEXUS بالكامل)

## الملخص التنفيذي

تحوّل النموذج إلى وكيل فعلي: طبقة `nexus/agents/` كاملة بأقسامها الستة كما في الخطة — التجريد (§6.1)، الحلقة (§6.2)، الوكيل الرئيسي (§6.3)، السجل (§6.4)، التواصل (§6.5)، والملكية (§6.6) — مربوطة بـ`NexusRuntime` ومقودة عبر آلة الحالات الثلاث عشرة. المرحلة بُنيت **مع** المستودعات المرجعية المسحوبة (جولة التكامل 2: langgraph · autogen · deepagents — MODE D مرجعية فقط، بلا أي استيراد من كودها؛ §0.4/§0.5 وقائمة المراقبة المكتوبة قبل بدء المرحلة)، والدليل 116/116 محليًا شاملًا انحدار المراحل 1–4 (98 · 143 · 104 · 106).

## 1 · Deliverables vs. Plan (مقابل الخطة)

| القسم | الخطة | المُسلَّم | الدليل |
|---|---|---|---|
| §6.1 Agent abstraction | 8 حقول حرفيًا: id · role · instructions · capabilities · tools · memory policy · model policy · verification | `nexus/agents/agent.py` — `AGENT_FIELDS` الثمانية بالترتيب + `MemoryPolicy` (سلّم §2.3) + `ModelPolicy` (توجيه §5.7 أو id صريح) + `VerificationPolicy` (حد إصلاح) | A — فحص الحقول الحرفي + round-trips |
| §6.2 Agent Loop | Observe → Context → Decide → Tool/Agent call → Observe → Verify → Continue | `nexus/agents/loop.py` — `LOOP_PHASES` السبعة حرفيًا، أثر `LoopStep` لكل مرحلة من كل دور، عقد قرار JSON صارم (`parse_decision` نقي) بمحاولة تصحيح واحدة، `ToolSink` (الدرز الذي سيدخله Tool Router لاحقًا)، بوابة تحقق كل دور (خفيفة) + بوابة كاملة عند done مع إصلاح محدود | B — أثر الدور 1 = السبعة بالترتيب، تعارض §6.6، حد الأدوار، فشل صادق |
| §6.3 Master Agent | 7 سلوكيات: يتعامل مع المستخدم · يفهم الهدف · يوزع العمل · يتابع · يستقبل النتائج · يقرر الاستمرار · يقرر الوصول إلى Verification | `nexus/agents/master.py` — `handle()` السلوكيات السبع موسومة «حرفيًا» في الكود، رقص الحالات ANALYZING→PLANNING→EXECUTING→VERIFYING→COMPLETED مع REPAIRING محدودة، الخطة على `task.plan.steps` (§2.5)، التحقق في `task.verification`، الإلغاء القانوني عند فشل النموذج مبكرًا | C — الرقص الكامل + مسار الإصلاح + استنفاد الإصلاح + الفشل المبكر |
| §6.4 Agent Registry | registerAgent · unregisterAgent · discoverAgents · getCapabilities | `nexus/agents/registry.py` — الأفعال الأربعة (snake_case باتفاقية الكود)، تخزين ذرّي `agents.registry.json` تحت `NexusPaths.data`، إعادة تحميل عند الإقلاع، القائمة مفتوحة، حماية سجل الرئيسي | D — الأفعال + الاستمرارية + الإقلاعين + ملف فاسد |
| §6.5 Agent Communication | 8 حقول: task_id · sender · receiver · type · status · data · evidence · confidence | `nexus/agents/messages.py` — `AGENT_MESSAGE_FIELDS` الثمانية حرفيًا، صناديق بريد لكل وكيل، دورة sent→delivered→read، بث `*`، سجل مُهيكل لكل مهمة + ترانسكربت JSONL بجوار سجل المهمة، `Evidence` وconfidence مقيدة 0..1 | E — الدورة + البث + الترانسكربت |
| §6.6 Agent Ownership | resource · owner — منع وكيلين من تعديل المورد نفسه بلا تنسيق | `nexus/agents/ownership.py` — `OWNERSHIP_FIELDS` حرفيًا، `acquire/release/release_owner/check/clear`، التعارض يرفع `ResourceOwnedError` حاملة المالك الحالي → رسالة coordination (لا كتابة فوق بعض أبدًا) | F — التعارض + التنسيق + التفكيك + الإغلاق |

## 2 · Exit criteria proof (إثبات معايير الخروج) — `tests/phase05/verify_exit_criteria.py`

```
PHASE 5 EXIT CRITERIA — 116/116 checks passed (0 failed)
```

- **A/§6.1**: الحقول الثمانية حرفيًا (dc_fields مقابل الثابت المستقل) · سياسات + تحقق رفض · round-trip · سجل الرئيسي.
- **B/§6.2**: الدورة السباعية حرفيًا من الأثر المسجّل · المحلل الصارم (9 حالات رفض + prose-wrapped + clamping) · حلقة كاملة على مزوّد مبرمج · مسار الأداة (أحداث + evidence) · تعارض §6.6 (رسالة تنسيق، لا tool.called، المالك سليم) · حد الأدوار (max_turns) · محاولة تصحيح واحدة بالضبط · فشل مزدوج → agent.failed · فشل النموذج → فشل صادق.
- **C/§6.3**: العقود الثلاثة (understanding/plan/verdict) نقية + رفض · المسار السعيد (الرقص الكامل + الخطوات + الوكلاء + سجل التحقق + الأحداث + الرسائل + تحرير الخانات) · إصلاح (VERIFYING→REPAIRING→VERIFYING→COMPLETED) · استنفاد الإصلاح (success=False بلا تزييف) · فشل مبكر (CANCELLED + خطأ مسجل) · حاجب الحالات النهائية.
- **D/§6.4**: الأفعال الأربعة · الاكتشاف (role/capability/بلا فلاتر) · الحماية · الاستمرارية الذرّية · إقلاعان · ملف فاسد لا يقتل الإقلاع.
- **E/§6.5**: الحقول الثمانية حرفيًا · دورة الحياة · البث · سجل لكل مهمة · الترانسكربت JSONL · تسلسل رتيب.
- **F/§6.6 + تكامل**: resource→owner حرفيًا · التعارض إشارة تنسيق · تكامل `NexusRuntime` (registry/communicator/ownership/master) · تشغيل كامل حتى COMPLETED على الـruntime · الترانسكربت بجوار المهمة · حفظ المهمة (§2.6) · حارس أسماء الأحداث (⊆28) · تحرير الملكية عند الإغلاق · إقلاع ثانٍ بلا تكرار الرئيسي · مفاتيح §6 الجديدة · تعطيل الرئيسي · **انحدار المراحل 1–4 كسوابقة subprocess: 98/98 · 143/143 · 104/104 · 106/106**.

## 3 · Quality gates (بوابات الجودة)

- `ruff check nexus/ tests/` — نظيف.
- `pyright nexus/` — 0 errors, 0 warnings.
- الحصانات: 98/98 · 143/143 · 104/104 · 106/106 · **116/116**.

## 4 · Documented design decisions (قرارات موثقة)

1. **الحلقة حرفية سباعية بكل دور**: الخطة ترسم الدورة بـObserve مرتين (قبل الفعل وبعده). الحلقة تسجّل `LoopStep` لكل مرحلة من كل دور — بقاء الدور الأخير (done) ينتهي عند بوابة التحقق (6 مراحل) لأن Continue لم يعد له معنى.
2. **التحقق طبقتان**: تحقق خفيف لسلامة الفعل كل دور (الدرس الحي من جولة 1: الفشل يُرصد مبكرًا) + البوابة الكاملة عند done (verifier قابل للحقن أو الفحص البنيوي: استجابة + evidence + معايير السياسة). الرئيسي يحتفظ بقرار الوصول إلى Verification (§6.3) والقرار النموذجي يقيّمه — لا تزييف أبدًا: فشل نموذج التحقق → COMPLETED بـsuccess=False وخطأ مسجل.
3. **عقد القرار JSON صارم بمحاولة تصحيح واحدة**: «لا قرار غير مفهوم» — الجواب خارج العقد يُرفض، يُعاد السؤال بملحوظة تصحيحية، والفشل الثاني فشل وكيل صادق. المحلل نقي (يُفحص بلا أي توصيل).
4. **ToolSink درز لا محرك**: §0.5 يضع Tool Registry/Tool Router في مراحل لاحقة — المرحلة 5 تسلّم `ToolSink`/`InlineToolSink` كواجهة الدخول الوحيدة للأدوات في الحلقة، والدور الأدوات يقيّدها بقائمة `agent.tools`. عند وصول Tool Router يستبدل الـsink خلف نفس الواجهة.
5. **الملكية داخل العملية (نطاق المرحلة)**: محرك التنفيذ أحادي الخيط (ملاحظة المرحلة 1: فقط الـEventBus آمن خيطيًا) — فالتطبيق داخل العملية كامل صادق للمرحلة 5؛ القفل بين العمليات يصل مع مراحل الأدوات على نفس عقد §6.6. التعارض **تنسيق لا تصادم**: رسالة COORDINATION تحمل المالك الحالي، والوكيل يعيد القرار (محكوم بحد الأدوار).
6. **السيد يقود آلة الحالات فقط عبر TaskEngine**: كل انتقال قانوني من جدول §2.4 — الوصول لـCOMPLETED لا يكون إلا عبر VERIFYING، وفشل النموذج مبكرًا يُلغي قانونيًا (CANCELLED من كل حالة غير نهائية) مع `agent.failed` وخطأ مسجل `master.understanding_failure` / `master.planning_failure`.
7. **استيرادات كسولة لمفردات core في master.py**: `nexus.core.config.runtime` يستورد `nexus.agents` على مستوى الوحدة — استيراد علوي لأي رمز core من master كان سيخلق دورة «وحدة نصف مهيأة» عند استيراد `nexus.agents` أولًا (برهان سيناريو الاستيراد المعكوس في الحصانة). الحل موثق في docstring الوحدة (نفس انضباط docstring `nexus.core.engine.__init__`).
8. **الترانسكربت JSONL بجوار سجل المهمة** (`tasks/<id>.messages.jsonl`): إلحاق فقط (append + fsync) — مُساعدة متانة لا عائق: فشل الكتابة تحذير لا استثناء. القالب لا يتعارض مع glob المستودع (`task_*.json`).
9. **مفاتيح §6 إضافية بDefaults** (`loop_max_turns` · `master_repair_limit` · `message_log_enabled`): نفس نمط المرحلة 4 — شجرة §2.1 الست بقيت متوافقة رجعيًا (98/98 يثبتها).
10. **المرجعيات المسحوبة لا تدخل الكود**: جلستا langgraph/autogen/deepagents في `vendor-staging` (MODE D) — أنماطها (شكل الحلقة، دلالات السجل، تدفق التفويض) استُرشدت بها في التصميم دون أي استيراد — إثبات §0.5/§0.4 من الكود: `rg "from (langgraph|autogen|deepagents)"` صفر نتائج.

## 5 · Inventory (الجرد)

```
nexus/agents/                     # §6 كاملة (7 وحدات)
├── __init__.py                   # 53 تصديرًا + خريطة الأقسام
├── agent.py                      # §6.1 التجريد (8 حقول + 3 سياسات + سجل الرئيسي)
├── registry.py                   # §6.4 الأفعال الأربعة + تخزين ذرّي
├── messages.py                   # §6.5 الرسائل + المُوجِّه + الترانسكربت
├── ownership.py                  # §6.6 الملكية (resource → owner)
├── loop.py                       # §6.2 الحلقة (الأثر السباعي + القرار + ToolSink)
└── master.py                     # §6.3 الرئيسي (7 سلوكيات + العقود الثلاثة)
tests/phase05/verify_exit_criteria.py   # 116/116
nexus/core/config/schema.py       # +3 مفاتيح agents (مع التحقق)
nexus/core/config/runtime.py      # ربط §6 + phase: 5 + تحرير الملكية عند الإغلاق
config/agents/agents.toml         # المفاتيح الجديدة موثقة
nexus/__init__.py                 # 0.5.0 · NEXUS_PHASE = 5
pyproject.toml                    # 0.5.0
.github/workflows/ci.yml          # harness المرحلة 5 + إصلاح فساد branches
```

## 6 · Reproduce (إعادة الإثبات)

```bash
python tests/phase05/verify_exit_criteria.py     # 116/116 (شامل انحدار 1–4)
ruff check nexus/ tests/                          # نظيف
pyright nexus/                                    # 0 أخطاء
```
