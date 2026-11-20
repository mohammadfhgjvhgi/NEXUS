<!-- ═══════════════════════════════════════════════════════════════════ -->
<!--  NEXUS — Legendary README · العربية أساسًا، English للتقنية والعالم  -->
<!-- ═══════════════════════════════════════════════════════════════════ -->

```text
███╗   ██╗███████╗██╗   ██╗██╗  ██╗██╗   ██╗███████╗
████╗  ██║██╔════╝██║   ██║██║ ██╔╝██║   ██║██╔════╝
██╔██╗ ██║█████╗  ██║   ██║█████╔╝ ██║   ██║███████╗
██║╚██╗██║██╔══╝  ██║   ██║██╔═██╗ ██║   ██║╚════██║
██║ ╚████║███████╗╚██████╔╝██║  ██╗╚██████╔╝███████║
╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝ ╚══════╝ ╚══════╝
```

<div align="center">

# حاسوبك. بعقل من جديد.

### Your computer. With a mind of its own.

**طبقة تشغيل ذكية فوق Windows — تعطيك الهدف، وتنجزه.**
**An intelligent execution layer above Windows — you give the goal, it delivers.**

</div>

<div align="center">

[![CI](https://github.com/PS-COMMUNITY/NEXUS/actions/workflows/ci.yml/badge.svg)](https://github.com/PS-COMMUNITY/NEXUS/actions/workflows/ci.yml)
[![Build](https://img.shields.io/badge/BUILD-PHASES%200–25%20COMPLETE-2da44e?style=flat-square&labelColor=1e1b2e)](docs/PROJECT-LOG.md)
[![Version](https://img.shields.io/badge/v0.25.0-NEXUS_PHASE%2025-8b5cf6?style=flat-square&labelColor=1e1b2e)](docs/PROJECT-LOG.md)
[![Platform](https://img.shields.io/badge/Windows-10%2B-0078D6?style=flat-square&logo=windows&logoColor=white&labelColor=1e1b2e)](#roadmap)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=1e1b2e)](#)
[![Runtime](https://img.shields.io/badge/AI-llama.cpp%20·%20local-d97a00?style=flat-square&labelColor=1e1b2e)](#systems)
[![Privacy](https://img.shields.io/badge/DATA-LOCAL--FIRST-2da44e?style=flat-square&labelColor=1e1b2e)](#principles)
[![License](https://img.shields.io/badge/License-MIT-c0c0c0?style=flat-square&labelColor=1e1b2e)](#license)
[![Spec](https://img.shields.io/badge/MASTER%20SPEC-375%20SECTIONS-8250df?style=flat-square&labelColor=1e1b2e)](docs/reference/NEXUS-Master-Technical-Specification-v1.0.md)

*Windows-first · Local-first · Model-agnostic · Goal-driven · Verification-first · Persistence-first*

</div>

---

## ⚡ هذا ليس مقترحًا — هذا مبنيّ · This is not a proposal — it is built

<div align="center">

| | | | |
|:---:|:---:|:---:|:---:|
| **26** | **2,152+** | **184** | **28** |
| مرحلة مكتملة<br>*phases done (0→25)* | فحص اختبار<br>*sandbox checks* | برهان حي<br>*live proofs* | حزمة نظام<br>*system packages* |
| **P8→P25** | **12** | **15** | **375** |
| براهين جهاز حقيقي<br>*device proofs sealed on disk* | قانونًا ذهبيًا<br>*golden engineering laws* | سلوكًا مُتحقَّقًا في المقارنة<br>*verified behaviors vs. the giants* | قسمًا في المواصفة المرجعية<br>*sections in the master spec* |

**كل رقم أعلاه مختوم بدليل على قرص جهاز Windows حقيقي — لا ادعاء واحد بلا مصدر.**
*Every number above is sealed with evidence on a real Windows machine's disk — not a single claim without a source.*

📖 **[السجل الكامل بالأرقام والمصادر · The full record with sources → docs/PROJECT-LOG.md](docs/PROJECT-LOG.md)**

</div>

---

## 🔥 لماذا NEXUS؟ · Why NEXUS?

<div dir="rtl">

**المشكلة:** كل مساعدات الذكاء الاصطناعي اليوم — ChatGPT وClaude وCopilot وDevin — هي إما **نافذة دردشة** تكتفي بالكلام، أو **وكيل سحابي** يعمل على أجهزة الآخرين وبياناتك عندهم. لا شيء منها يجلس على **حاسوبك أنت**، يرى شاشتك، يلمس تطبيقاتك، ويعمل على هدفك حتى ينتهي — وينجو من انقطاع الكهرباء في المنتصف.

**NEXUS** هو الجواب: وكيل حكم ذاتي **محلي بالكامل** فوق Windows — يفهم الهدف، يخطط، ينفذ بأدوات حقيقية (UIA · متصفح · طرفية · ملفات · رؤية)، **يراقب نفسه**، يتحقق بالأدلة، يصلح أخطاءه، يحفظ تقدمه على القرص، ويتعلم من كل تجربة. النماذج محلية (llama.cpp) — بياناتك لا تغادر الجهاز.

</div>

**The problem:** every AI assistant today is either a **chat window** that talks, or a **cloud agent** that runs on someone else's machine with your data. Nothing sits on **your** computer, sees your screen, touches your apps, and works your goal to completion — surviving a power cut mid-task.

**NEXUS** is the answer: a fully **local** autonomous agent above Windows — it understands the goal, plans, executes with real tools (UIA · browser · terminal · files · vision), **watches itself**, verifies with evidence, repairs its own failures, checkpoints progress to disk, and learns from every run. Models run locally via llama.cpp — your data never leaves the machine.

### ماذا يفعل فعليًا؟ · What it actually does

| | القدرة · Capability | كيف · How |
|:---:|---|---|
| 🎯 | **يعمل حتى يكتمل الهدف** · *Works until the goal is done* | Long-Horizon engine — الهدف على القرص، عامل خلفي حقيقي، نقاط تفتيش دورية، استئناف لا يثق بالذاكرة، مهلة جدارية صادقة *(§25)* |
| 💻 | **يتحكم بـ Windows فعليًا** · *Actually controls Windows* | هرمية §9.5: Native API → UIA → DOM → Vision → Mouse/Keyboard — بتراجع مُتتبَّع وoverlay مرئي |
| 🛡️ | **لا يتوقف صامتًا أبدًا** · *Never stalls silently* | نبض على 7 مكوّنات مشتق من الساعة، كشف علوق بأربع بصمات، سلّم استعادة خماسي *(§23)* |
| 🔁 | **ينجو من إعادة التشغيل** · *Survives reboot & power loss* | Checkpoints ذرية بأربعة نطاقات + فحص الواقع الفعلي قبل الاستئناف — «الملفات تحسم» *(§22)* |
| 👥 | **نظام وكلاء لا وكيل واحد** · *An agent system, not one agent* | Master + 13 متخصصًا، توازٍ بثلاث بوابات، ملكية خماسية لكل وكيل *(§24)* |
| 🧠 | **يتعلم من التجربة** · *Learns from experience* | مستخلص تجارب بستة أنواع → ترقية مهارات عبر محرك الذاكرة بـ12 نطاقًا *(§12/§13)* |

---

## ⚔️ الفارق · The Difference

<div dir="rtl">

وليس **15** سلوكًا يفصل NEXUS عن أعمدة المجال — مقارنة صادقة، كل ✅ هنا خلفها اختبارات وبراهين في هذا المستودع نفسه:

</div>

Fifteen behaviors separate NEXUS from the field — an honest matrix where every ✅ is backed by tests and proofs **in this very repository**:

| السلوك · Behavior | ChatGPT | Copilot | Devin | **NEXUS** |
|---|:---:|:---:|:---:|:---:|
| إجابات حوارية · Conversational answers | ✅ | ⚠️ | ❌ | ✅ |
| كتابة كود فعلي · Writes real code | ❌ | ✅ | ❌ | ✅ |
| يشتغل حتى الهدف · Runs until **goal** done | ❌ | ⚠️ | ⚠️ scripted | ✅ Long-Horizon *(§25)* |
| تحقق بالأدلة · Verifies with evidence | ❌ | ⚠️ | ❌ | ✅ Verification-first *(§20)* |
| ينجو من إعادة التشغيل · Survives reboot & power loss | ❌ | ❌ | ❌ | ✅ Checkpoints + Recovery *(§22)* |
| لا يتوقف صامتًا · Never stalls silently | ❌ | ❌ | ❌ | ✅ Heartbeat + Health *(§23)* |
| يتعلم من التجربة · Learns from experience | ❌ | ❌ | ❌ | ✅ Learning Engine *(§13)* |
| نماذج محلية · Local-first models | ⚠️ | ❌ | n/a | ✅ llama.cpp *(§6)* |
| يتحكم بتطبيقات Windows · Controls Windows apps | ❌ | ❌ | ⚠️ brittle | ✅ API→UIA→Vision *(§9)* |
| إنسان وAI بالتوازي · Human + AI in parallel | ❌ | ❌ | ⚠️ | ✅ Input Ownership *(§10)* |
| تخطيط متعدد الوكلاء · Multi-agent orchestration | ❌ | ⚠️ | ❌ | ✅ Master + 13 Specialists *(§24)* |
| أمان بطبقات وخزنة أسرار · Layered security + secret vault | ❌ | ⚠️ | ⚠️ | ✅ Scope→Permission→Gate *(§21)* |
| بحث بمصادر مُصنَّفة ومُحصَّدة · Research with classified sources | ⚠️ | ❌ | ⚠️ | ✅ 8-stage workflow *(§17)* |
| مستندات DOCX/PPTX/PDF حقيقية · Real document verbs | ⚠️ | ⚠️ | ❌ | ✅ real OOXML *(§18)* |
| صوت عربي/إنجليزي مُعيارَيَّن · Benchmarked Arabic/English speech | ❌ | ❌ | ❌ | ✅ WER/CER six conditions *(§19)* |

---

<a id="principles"></a>

## 🧭 المبادئ التسعة · The Nine Non-Negotiables

| # | Principle · المبدأ | المعنى · Meaning |
|:---:|---|---|
| 1 | **Goal-first** | الهدف النهائي أهم من أي سلسلة خطوات ثابتة — the end goal outranks any fixed sequence |
| 2 | **Prompt priority** | `Current Prompt > Task Constraints > Workspace Policy > Project Decisions > User Preferences > Long-term Learning` |
| 3 | **Task-scoped capability** | القدرات الواسعة مرتبطة بالمهمة لا تُستعمل عشوائيًا — wide capability, task-bound |
| 4 | **Verification-first** | إعلان النجاح يتطلب دليلًا فعليًا — success claims need evidence *(§20)* |
| 5 | **Persistence-first** | المهمة تنجو من النوافذ والإقلاعات وانقطاع الكهرباء — tasks survive reboots *(§22/§25)* |
| 6 | **Local-first** | النواة والنماذج والذاكرة والحالة — على الجهاز — core stays on the machine |
| 7 | **Model-agnostic** | لا ارتباط بنموذج محدد — no hard model dependency |
| 8 | **Composable** | كل Agent/Tool/Model/Skill/Plugin خلف عقد صريحة — explicit contracts *(§8)* |
| 9 | **Graceful degradation** | نقص الموارد ⇒ تباطؤ لا خسارة — slowness beats losing the task |

<div align="center">

> **النموذج ليس المدير. NEXUS Core هو المدير.**
> **The model is not the manager. NEXUS Core is the manager.** *(Spec §364)*

</div>

---

<a id="architecture"></a>

## 🏗️ المعمارية · Architecture

<div dir="rtl">

معمارية **Super-Harness**: نواة NEXUS ملك خالص، وكل مشاريع المصادر المفتوحة تدخل خلف **Adapters** — يموت المستودع الخارجي؟ نستبدل الـAdapter ويستمر NEXUS *(Spec §266–267)*.

</div>

A **Super-Harness** architecture: the NEXUS Core is fully ours; every open-source component sits **behind adapters** — an external repo dies? Swap the adapter, NEXUS continues *(Spec §266–267)*.

```text
                         ┌──────────────────────┐
                         │        USER          │
                         │ Text / Voice / Files │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │      NEXUS UI        │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │    MASTER AGENT      │  ← الباب الوحيد للمستخدم (§24.1)
                         └──────────┬───────────┘
                                    ▼
                    ┌──────────────────────────────┐
                    │      NEXUS ORCHESTRATOR      │
                    │ Goal / Scope / Plan / State  │
                    └──────────────┬───────────────┘
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
┌───────────────┐          ┌────────────────┐          ┌────────────────┐
│ AGENT SYSTEM  │          │ MEMORY/LEARNING│          │ RESOURCE SYSTEM│
│ Planner       │          │ 12 scopes (§12)│          │ CPU / RAM      │
│ Research      │          │ Lessons/Skills │          │ GPU / VRAM     │
│ Coding        │          │ Promotion (§13)│          │ Concurrency    │
│ Browser       │          └───────┬────────┘          └───────┬────────┘
│ Computer      │                  │                           │
│ Testing/Sec   │                  │                           │
└──────┬────────┘                  │                           │
       └───────────────────────────┼───────────────────────────┘
                                   ▼
                          ┌──────────────────┐
                          │   TOOL ROUTER    │  ← 7 مراحل مُتتبَّعة (§8.2)
                          └────────┬─────────┘
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
              Native            MCP             Plugins
               Tools             Tools             Tools
                                   ▼
                         ┌────────────────────┐
                         │ COMPUTER RUNTIME   │
                         │ Windows UIA · Browser│
                         │ Terminal · Files    │
                         │ Mouse/Keyboard     │
                         │ Vision/OCR · Procs │
                         └─────────┬──────────┘
                                   ▼
                              WINDOWS PC
                                   ▼
                          OBSERVE + VERIFY (§20)
                       ┌───────────┴───────────┐
                       ▼                       ▼
                    SUCCESS                  REPAIR ──▶ EXECUTE
                       │
                       ▼
                  CHECKPOINT (§22) ──▶ MEMORY/LEARNING (§12/§13) ──▶ CONTINUE
                       │
                       ▼
               FINAL VERIFICATION ──▶ RESULT
```

### هرمية التحكم بـ Windows · Windows control hierarchy

```text
1. Native / Application API        ← الأعلى موثوقية · most reliable
2. Windows UI Automation (UIA)     ← accessibility tree · native ctypes client
3. Browser / DOM Automation        ← Playwright «USE» behind the router
4. Vision                          ← screen understanding via capture + OCR/VLM
5. Mouse / Keyboard                ← الملاذ الأخير، مع overlay مرئي · last resort, visible overlay
```

<div dir="rtl">

دائمًا الطبقة الأعلى موثوقية أولًا — والتراجع لكل درجة **مُسجَّل ومُتتبَّع**، لا صمت أبدًا *(Spec §59, §9.5)*.

</div>

Always the most reliable layer first — and every fallback is **traced**, never silent *(Spec §59, §9.5)*.

---

<a id="systems"></a>

## 📦 ما الذي بُني فعلاً؟ · The 28 Built Packages

<div dir="rtl">

28 حزمة نظام حية تحت `nexus/` — كل واحدة بعقد صريحة، اختبارات، وبرهان حي. ليست شعارات:

</div>

28 living system packages under `nexus/` — each with explicit contracts, tests, and live proofs. Not logos:

| | | |
|---|---|---|
| **`core`** آلة حالات 13 حالة · sessions · persistence *(P1)* | **`events`** ناقل 28 حدثًا قانونيًا *(P1)* | **`workspace`** سجل مساحات 7 حقول *(P2)* |
| **`resources`** عتاد 12 هدف فحص + مدير موارد *(P3)* | **`models`** llama.cpp runtime محلي *(P4)* | **`agents`** الوكيل + الحلقة + الماستر *(P5)* |
| **`harness`** §41 · skills · rules · hooks *(P6)* | **`tools`** سجل 9 حقول + موجّه 7 مراحل + MCP v2 *(P7)* | **`computer`** 8 نطاقات تحكم Windows *(P8)* |
| **`windows`** نوافذ · ملكية إدخال · overlay *(P9)* | **`browser`** Playwright معزول + خزنة DPAPI *(P10)* | **`vision`** التقاط + OCR مُعيارَيَّن *(P11)* |
| **`memory`** 12 نطاقًا · Qdrant · سلّم نزاع *(P12)* | **`learning`** تجارب → مهارات *(P13)* | **`codeintel`** AST · رسوم · خرائط PageRank *(P14)* |
| **`coding`** حلقة 8 مراحل · 10 متخصصين *(P15)* | **`git`** 8 عمليات + rollback آمن *(P16)* | **`github`** 8 عمليات · PR · release *(P16)* |
| **`research`** 8 مراحل · مصادر مُصنَّفة *(P17)* | **`documents`** DOCX · PPTX · PDF حقيقية *(P18)* | **`speech`** sherpa-onnx + SAPI · WER/CER *(P19)* |
| **`verification`** أدلة sha256 مختومة *(P20)* | **`security`** Scope→Permission→Gate · Trivy *(P21)* | **`recovery`** checkpoints + No Blind Resume *(P22)* |
| **`health`** نبض 7 مكوّنات + كشف علوق *(P23)* | **`orchestration`** Master + 13 متخصصًا *(P24)* | **`horizon`** أهداف طويلة الأمد تنجو من reboot *(P25)* |

---

## ⚖️ القوانين الذهبية · The Golden Laws

<div dir="rtl">

صيغت من فشل حقيقي — كل قانون درسٌ كلف اختبارًا فاشلًا كان سيكذب لولا القاعدة:

</div>

Distilled from real failures — each law cost a test that would have lied without it:

| # | القانون · Law |
|:---:|---|
| 1 | **القرص يحسم لا الذاكرة** — every worker decision re-reads the file *(§25)* · *The disk decides, not memory* |
| 2 | **دليل أو لم يحدث** — no ✅ without evidence · *Evidence or it didn't happen* |
| 3 | **الرفض الصادق أفضل من نجاح مزيف** — SKIP is an honest refusal *(§20/§19)* |
| 4 | **كل رفض يسمّي سببه** — every denial names its reason *(§24.3/§25.6)* |
| 5 | **لا استئناف أعمى** — resume reads reality from disk first *(§22.4)* |
| 6 | **الصمت حكم الساعة لا الاستثناء** — stall is derived from the clock *(§23)* |
| 7 | **السر لا يغادر الخزنة** — `SecretLeakError` is the hard stop *(§21)* |
| 8 | **بوابة التوازي الثلاثية** — tasks independent ∧ files independent ∧ resources available *(§24.3)* |
| 9 | **الملكية الخماسية** — task · scope · parent · children · owned resources *(§24.4)* |
| 10 | **المهلة تحدّ تشغيلاً واحدًا** — a deadline is a wall, never a fake completion *(§25.7)* |
| 11 | **CI خضراء هي الحكم الأخير** — green CI is the final judge |
| 12 | **التكامل لا التكرار** — integrate, never duplicate *(§22/§23 reused verbatim in §24/§25)* |

---

## 🖥️ الجهاز · Built on a Real Machine

<div dir="rtl">

كل برهان «على الجهاز» في هذا المستودع يعني هذا الجهاز بالذات — لا محاكاة، لا ادعاء:

</div>

Every "device proof" in this repository means **this** machine — no simulation, no hand-waving:

| الحقل · Field | القيمة · Value |
|---|---|
| الهوية · Identity | **almoutmag-v9** |
| النظام · OS | Windows 10 · 10.0.19045 · AMD64 |
| بايثون · Python | 3.14.5 |
| بصمة الحماية · Fingerprint | `a5a2e62a821bec53` |
| قرص البراهين · Proof disk | `M:\NEXUS\proofs\` — JSON مختوم بالوقت والهوية لكل مرحلة |

---

<a id="roadmap"></a>

## 🗺️ خارطة الطريق · Roadmap

<div dir="rtl">

خطة البناء تفرض **40 مرحلة تنفيذية** من تجهيز الجهاز حتى التغليف الإنتاجي *(Build Plan §1–§40)* — والمرحلة التالية بعد 25 هي **MIDPOINT: أول NEXUS.exe حقيقي**.

</div>

The Build Plan mandates **40 executable phases** *(Build Plan §1–§40)* — after 25, the next stop is **MIDPOINT: the first real NEXUS.exe**.

| Deliverable · المخرَج | Progress |
|---|---|
| Master Specification v1.0 (375 sections) | `██████████ 100%` ✅ |
| Final Build Plan v1.0 (109 sections) | `██████████ 100%` ✅ |
| PHASE 0 — Machine & Repository Preparation | `██████████ 100%` ✅ |
| **PHASE 1 — NEXUS Core Foundation** · config · event bus · sessions · task engine · persistence | `██████████ 100%` ✅ |
| **PHASE 2 — Workspace + Scope + Policy** | `██████████ 100%` ✅ |
| **PHASE 3 — Hardware Intelligence + Resource Manager** | `██████████ 100%` ✅ |
| **PHASE 4 — Local Model Runtime** · llama.cpp | `██████████ 100%` ✅ |
| **PHASE 5 — Agent Runtime** · agent · loop · master · registry · messages · ownership | `██████████ 100%` ✅ |
| **PHASE 6 — Harness Integration** · ECC/Cline/LangGraph/Prime/DeepAgents patterns | `██████████ 100%` ✅ |
| **PHASE 7 — Tool System** · Tool Registry (9 fields) · Tool Router (7-stage traced) · MCP SDK v2 behind the router | `██████████ 100%` ✅ |
| **PHASE 8 — Windows Computer Runtime** · Computer API (8 domains) · §9.5 fallback hierarchy (5 layers) · native UIA · SendInput | `██████████ 100%` ✅ |
| **PHASE 9 — Window Manager + Human Parallelism** · Window Registry · USER/NEXUS/SHARED ownership · per-window input arbitration · ctypes overlay | `██████████ 100%` ✅ |
| **PHASE 10 — Browser Runtime** · Playwright MODE A «USE» · channel ladder · isolated sessions · DPAPI vault + vault_ref · self-healing selectors | `██████████ 100%` ✅ |
| **PHASE 11 — Vision + OCR + Screen Understanding** · Screen Capture (pure ctypes) · VisionProvider · OCR engine race (device benchmark decides) | `██████████ 100%` ✅ |
| **PHASE 12 — Memory System** · 12-scope hierarchy · SQLite index · Qdrant MODE A · Mem0 MODE B · §12.8 conflict ladder | `██████████ 100%` ✅ |
| **PHASE 13 — Learning System** · Experience Extractor (six kinds) · six-stage pipeline → §12 promotion · SkillCandidate + WorkflowMiner | `██████████ 100%` ✅ |
| **PHASE 14 — Code Intelligence** · File/Symbol Index · 3-engine AST · Dependency/API/Test graphs · Aider PageRank maps · 100k-scale | `██████████ 100%` ✅ |
| **PHASE 15 — Coding System** · Coding Agent Contract (7 ops) · ten specialists · eight-stage loop · Cline-style session trail | `██████████ 100%` ✅ |
| **PHASE 16 — Git / GitHub** · Git Engine (8 ops) · GitHub Engine (8 ops) · Repository Lifecycle · Parallel Agents | `██████████ 100%` ✅ |
| **PHASE 17 — Research Engine** · one SearchProvider contract (5 surfaces) · 8-stage workflow with verdicts · source classification + confidence | `██████████ 100%` ✅ |
| **PHASE 18 — Document Intelligence** · Docling MODE A/B · inverted SQLite index · real DOCX/PPTX/PDF verbs | `██████████ 100%` ✅ |
| **PHASE 19 — Speech System** · SpeechProvider · sherpa-onnx + SAPI floor · 6-condition WER/CER benchmark · mic→intent→task pipeline | `██████████ 100%` ✅ |
| **PHASE 20 — Verification Engine** · PASS/FAIL/ERROR/SKIP · 9 domains with real probes · sha256-sealed evidence · repair loop | `██████████ 100%` ✅ |
| **PHASE 21 — Security System** · Scope→Permission→Gate · risk ladder · tool/MCP/plugin gates · secret vault · redaction · audit · Trivy | `██████████ 100%` ✅ |
| **PHASE 22 — Recovery + Checkpoints** · 4-scope checkpoint manager · 6 triggers · recovery chain · **No Blind Resume** | `██████████ 100%` ✅ |
| **PHASE 23 — Heartbeat + Health** · 7-component heartbeat · 4-signal stall detection · 5-rung recovery ladder | `██████████ 100%` ✅ |
| **PHASE 24 — Multi-Agent Orchestration** · Master-only user channel · 13 specialists · 3 conjunctive parallelism gates · 5-field ownership | `██████████ 100%` ✅ |
| **PHASE 25 — Long-Horizon Execution** · goal persistence + journal · background workers · durable state ladder · per-step heartbeat · periodic checkpoints · no-blind resume · wall-clock deadlines | `██████████ 100%` ✅ |
| **▶ NEXT — MIDPOINT · NEXUS Windows Product v0.1** · NEXUS.exe (Launcher → Core → UI) · first real chat · first real task · build via tunnel → `M:\NEXUS\build\` · first real run · installer preview · desktop UI · tray · overlay · **MIDPOINT GATE (10 checks)** | `░░░░░░░░░░` |
| PHASE 26 — Desktop UI Production | `░░░░░░░░░░` |
| PHASE 27 — Tray + Startup Production | `░░░░░░░░░░` |
| PHASE 28 — Remote Web | `░░░░░░░░░░` |
| PHASE 29 — Realtime Remote | `░░░░░░░░░░` |
| PHASE 30 — Plugin System | `░░░░░░░░░░` |
| PHASE 31 — Skill System | `░░░░░░░░░░` |
| PHASE 32 — Model Learning / Fine-tuning (optional) | `░░░░░░░░░░` |
| PHASE 33 — Computer-use Evaluation | `░░░░░░░░░░` |
| PHASE 34 — Browser Evaluation | `░░░░░░░░░░` |
| PHASE 35 — Full System Verification | `░░░░░░░░░░` |
| PHASE 36 — Fault Injection | `░░░░░░░░░░` |
| PHASE 37 — Recovery Validation | `░░░░░░░░░░` |
| PHASE 38 — Final Security Audit | `░░░░░░░░░░` |
| PHASE 39 — Performance Optimization | `░░░░░░░░░░` |
| PHASE 40 — Production Packaging | `░░░░░░░░░░` |

> ⚠️ **موقف CI بصدق · Honest CI note:** أعمال CI الأخيرة فشلت قبل checkout بصفر خطوات بسبب عطل فوترة حسابي موروث — لا بكود المشروع. الوثائق والاختبارات وبراهين الجهاز كلها خضراء ومختومة. *The latest CI runs fail before checkout with zero steps due to an inherited account-billing fault — not project code. Docs, tests, and device proofs are all green and sealed.* → [PROJECT-LOG.md](docs/PROJECT-LOG.md)

---

<a id="done"></a>

## 🏁 معيار الاكتمال · Definition of Done

<div dir="rtl">

NEXUS لا يعتبر منتهيًا عندما "تعمل الواجهة" — بل عندما ينجح في *(Spec §361)*:

</div>

NEXUS is not finished when the UI works — it is finished when it succeeds at *(Spec §361)*:

```text
Understand + Plan + Execute + Observe + Verify + Repair + Persist + Recover + Learn
```

<div dir="rtl">

عبر: **الملفات · تطبيقات Windows · المتصفح · الطرفية · الكود · GitHub · المستندات · المهام الطويلة**

> **«أعطيك الهدف، وتنجزه.»** — بأقل تدخل ممكن.

</div>

across: **Files · Windows apps · Browser · Terminal · Code · GitHub · Documents · Long tasks**

> **"You give the goal — NEXUS delivers."** — with minimal intervention.

---

## ❓ FAQ · أسئلة شائعة

<details>
<summary><b>هل NEXUS عبارة عن Chatbot؟ · Is NEXUS a chatbot?</b></summary>

<div dir="rtl">لا. الشات واجهة واحدة فقط. المحرك هو Task/Agent/Computer Runtime الذي يحوّل الهدف إلى عمل فعلي.</div>
No. Chat is just one interface. The engine is the Task/Agent/Computer Runtime that turns goals into real work.
</details>

<details>
<summary><b>هل يحتاج إنترنت؟ · Does it need internet?</b></summary>

<div dir="rtl">Local-first: النواة والنماذج والذاكرة تعمل بلا إنترنت. ما يحتاج الشبكة يدخل WAITING_NETWORK ويستأنف تلقائيًا عند عودتها.</div>
Local-first: core, models, and memory work offline. Network-dependent work enters <code>WAITING_NETWORK</code> and auto-resumes.
</details>

<details>
<summary><b>ماذا لو انقطعت الكهرباء وسط مهمة؟ · What if power is lost mid-task?</b></summary>

<div dir="rtl">Checkpoint ▶ إقلاع ▶ كشف المهمة المقاطعة ▶ فحص الواقع الفعلي (الملفات تحسم) ▶ استئناف من آخر نقطة مؤكدة.</div>
Checkpoint ▶ boot ▶ detect interrupted task ▶ inspect reality (filesystem wins) ▶ resume from the last reconciled point.
</details>

<details>
<summary><b>هل بياناتي تغادر الجهاز؟ · Does my data leave the machine?</b></summary>

<div dir="rtl">النواة محلية 100%. الاستشارة الخارجية اختيارية وتمر بتصنيف وتنقية بيانات قبل أي إرسال — والأسرار لا تغادر الخزنة أبدًا (§21).</div>
The core is 100% local. External consultation is optional and passes classification + redaction first — and secrets never leave the vault (§21).
</details>

<details>
<summary><b>لماذا نموذج صغير؟ لماذا لا GPT؟ · Why a small local model?</b></summary>

<div dir="rtl">لأن NEXUS Core هو المدير لا النموذج: التخطيط والتحقق والاستعادة بنيوية في المحرك. النموذج الصغير المحلي يكفي للاستدلال اليومي، والخصوصية والعمل دون إنترنت ليستا خيارًا بل تصميمًا. وModel-agnostic: نموذج أكبر = أداء أعلى، بنفس العقود.</div>
Because the NEXUS Core is the manager, not the model: planning, verification, and recovery are structural in the engine. A small local model suffices for daily inference; privacy and offline operation are design, not option. And model-agnostic: a bigger model = more performance, same contracts.
</details>

<details>
<summary><b>كيف أثبت أن كل هذا مبني فعلاً؟ · How do I know this is actually built?</b></summary>

<div dir="rtl">ثلاثة مصادر: تقرير مرحلي لكل مرحلة (docs/PHASE-*-REPORT.md) · اختبارات قابلة للتنفيذ (tests/phase25/) · براهين JSON مختومة على قرص الجهاز (M:\NEXUS\proofs\). والسجل الكامل: docs/PROJECT-LOG.md.</div>
Three sources: a report per phase (docs/PHASE-*-REPORT.md) · runnable tests (tests/) · sealed JSON proofs on the machine's disk (M:\NEXUS\proofs\). The full record: docs/PROJECT-LOG.md.
</details>

<details>
<summary><b>لماذا بايثون 3.14؟ · Why Python 3.14?</b></summary>

<div dir="rtl">لأن هذا مشروع Windows-first يُبنى على أحدث runtime مستقر، والنواة stdlib-only بلا استثناء — التبعيات الثقيلة خلف Adapters وبأوضاع A–F موثقة.</div>
Because this is a Windows-first project built on the latest stable runtime, and the core is stdlib-only without exception — heavy dependencies live behind adapters in documented MODE A–F.
</details>

<details>
<summary><b>متى NEXUS.exe؟ · When NEXUS.exe?</b></summary>

<div dir="rtl">التالي فورًا: MIDPOINT — أول NEXUS.exe حقيقي (Launcher → Core → UI) متصل بالنواة الموجودة، بـ17 خطوة وبوابة خروج بعشرة معايير قبل PHASE 26.</div>
Immediately next: MIDPOINT — the first real NEXUS.exe (Launcher → Core → UI) wired to the existing core, 17 steps and a 10-check gate before PHASE 26.
</details>

---

<a id="docs"></a>

## 📚 التوثيق · Documentation

| Document | الوصف · Description |
|---|---|
| 📖 [**PROJECT-LOG.md**](docs/PROJECT-LOG.md) | ⭐ **سجل الإنجاز 0→25** — لوحة الأرقام، القوانين الذهبية، سجل كل مرحلة بإثباتها، مصدر كل رقم |
| 📜 [**NEXUS Master Technical Specification v1.0**](docs/reference/NEXUS-Master-Technical-Specification-v1.0.md) | **مصدر الحقيقة الوحيد** — 375 قسمًا: الرؤية، المعمارية، Task Model، الذاكرة، التعلم، Computer/Browser Runtimes، التحقق، الاستعادة، الأمان، APIs، العقود |
| 🧭 [**NEXUS Final Build Plan v1.0**](docs/reference/NEXUS-Final-Build-Plan-v1.0.md) | **أمر التنفيذ الإجباري** — 109 أقسام: Integration Modes A–F، قاعدة الـAdapter، الترتيب الإجباري، معايير الاكتمال |
| 🔌 [**Repository Integration Record**](docs/REPOSITORY-INTEGRATION.md) | سجل دخول كل مستودع خارجي: تدقيق ترخيص، مراجعة أمنية، وضع تكامل A–F، دبوس إصدار، وبرهانه الحي — 12 جولة |
| 📋 [**CHANGELOG.md**](CHANGELOG.md) | كل تغيير جوهري، مرحلة بمرحلة |
| 📄 `docs/PHASE-*-REPORT.md` | تقرير مستقل لكل مرحلة — ما بُني وكيف أُثبت |
| 🧠 `docs/nexus-spec/` | قاعدة المعرفة الدائمة — تغطية 100% لأقسام المواصفة |

> ⚖️ **قاعدة المستودع · Rule of the repo:** المواصفة هي مصدر الحقيقة الوحيد (ماذا نبني)، وخطة البناء هي أمر التنفيذ (كيف وبأي ترتيب). أي كود يخالفهما **Bug** — أو يتطلب مراجعة موثقة أولًا. *The Master Specification is the single source of truth (what); the Final Build Plan is the execution order (how). Any code that conflicts with either is a **bug** — or requires an explicit, documented revision first.*

---

<a id="contributing"></a>

## 🤝 المشاركة · Contributing

<div dir="rtl">

أفضل مساهماتك الآن — بنفس فلسفة NEXUS: خطة ▶ تنفيذ ▶ تحقق:

</div>

The best contributions right now — NEXUS's own philosophy applied to contributors:

1. 📖 **راجع المواصفة** — [375 قسمًا](docs/reference/NEXUS-Master-Technical-Specification-v1.0.md) مقابل قائمة المراجعة النهائية للخبراء *(Spec §374)* — وافتح Issue لأي ثغرة أو تناقض
2. 🐛 **اختبر البراهين** — نفّذ الاختبارات بنفسك: `pytest tests/` — كل رقم في هذا الريديم قابل لإعادة الإنتاج
3. 🔌 **رشّح مستودعًا** لجولة تكامل قادمة — عبر دورة §0.2 الكاملة في [سجل التكامل](docs/REPOSITORY-INTEGRATION.md)
4. 💡 **اقترح عبر Issues** قبل أي PR — وكل PR يمر بـ Plan ▶ Implement ▶ Verify

---

<a id="license"></a>

## ⚖️ License · الترخيص

[MIT](LICENSE) — © 2026 PS-COMMUNITY — The NEXUS Project

---

<div align="center">

**NEXUS v0.25.0 — 26 مرحلة. حلقة تنفيذ واحدة. صفر ادعاءات بلا دليل.**

*26 phases. One execution loop. Zero claims without evidence.*

```
القرص يحسم. الدليل يتكلم. CI هي الحكم الأخير.
The disk decides. Evidence speaks. Green CI is the final judge.
```

**التالي · NEXT → `NEXUS.exe`** 🚀

</div>
