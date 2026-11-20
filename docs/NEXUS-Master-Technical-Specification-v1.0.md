# 0. حالة الوثيقة

**اسم المنتج:** NEXUS  
**الاسم الوصفي:** NEXUS — Local Autonomous Computer Intelligence Platform  
**نوع المنتج:** Windows-first Local Autonomous Agent Platform  
**المنصة المستهدفة:** Windows 10 Pro كبداية، مع تصميم يسمح بالترقية مستقبلًا دون إعادة بناء النواة.  
**حالة الوثيقة:** المواصفة الرئيسية المرجعية للمنتج النهائي.  
**الغرض:** إعطاء فريق هندسي أو خبراء برمجيات وAI وWindows Automation تعريفًا كاملًا لما يجب أن يكون عليه NEXUS، وكيف يجب أن يعمل، وما حدوده، وكيف تتصل مكوناته، وما الذي سيأتي من المشاريع المفتوحة وما الذي يجب أن تمتلكه NEXUS نفسه.

---

# 1. الرؤية النهائية للمنتج

NEXUS ليس Chatbot، وليس Coding Agent فقط، وليس Browser Agent فقط، وليس Remote Desktop فقط.

NEXUS هو:

> **طبقة تشغيل ذكية فوق Windows، تجعل الكمبيوتر بيئة تنفيذ لوكيل ذكاء اصطناعي محلي قادر على تحويل هدف المستخدم إلى نتيجة مكتملة، مع التخطيط، البحث، التنفيذ، التحكم بالكمبيوتر، الذاكرة، التحقق، الإصلاح، الاستعادة، التعلم، والتوسع.**

الصورة المفاهيمية:

```text
USER
  │
  ├── Text
  ├── Voice
  ├── Files
  └── Images
  │
  ▼
NEXUS UI
  │
  ▼
MASTER AGENT
  │
  ▼
ORCHESTRATOR
  │
  ├───────────────┬────────────────┬────────────────┐
  ▼               ▼                ▼                ▼
AGENT SYSTEM   MEMORY SYSTEM   TOOL SYSTEM    RESOURCE SYSTEM
  │               │                │                │
  ▼               ▼                ▼                ▼
Specialists    Context         Native/MCP       CPU/RAM/GPU
Subagents      Knowledge       Plugins          VRAM
  │               │                │
  └───────────────┴────────────────┘
                  │
                  ▼
          COMPUTER RUNTIME
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
      Windows   Browser   Terminal
      Apps      Web       Shell
        │         │         │
        └─────────┼─────────┘
                  ▼
              WINDOWS
                  │
                  ▼
          OBSERVE + VERIFY
                  │
          ┌───────┴───────┐
          ▼               ▼
       SUCCESS          REPAIR
          │               │
          ▼               └──────► EXECUTE
     CHECKPOINT
          │
          ▼
    MEMORY + LEARNING
          │
          ▼
       CONTINUE
          │
          ▼
    FINAL VERIFICATION
          │
          ▼
        RESULT
```

---

# 2. الأهداف الأساسية

NEXUS يجب أن يحقق الأهداف التالية:

## 2.1 الهدف الوظيفي

المستخدم يستطيع أن يقول:

> "ابنِ لي تطبيق."

أو:

> "افتح Word واعمل التقرير."

أو:

> "حلل المشروع الموجود على القرص M وطوره."

أو:

> "ابحث عن أفضل 10 repositories لهذا النوع من المشاريع، حللها واختر أفضلها."

أو:

> "حلل مواصفات جهازي واضبط إعدادات اللعبة أو التطبيق."

ولا يتطلب ذلك تقسيم المهمة إلى عشرات الأوامر الصغيرة.

---

# 3. متطلبات المنتج

المتطلبات الأصلية تحدد أن NEXUS يجب أن يدير الملفات والمجلدات والأقراص والبرامج والتطبيقات والطرفية والمتصفح والمستندات وأدوات الجهاز، وأنه يستطيع إنشاء المشاريع وتطويرها وتشغيلها واختبارها وإصلاحها.

كما أن المتطلبات تنص على دعم بناء التطبيقات والمواقع والمنصات، المشاريع البرمجية الكبيرة، البحث، قراءة المستندات، المتصفح، تطبيقات Windows، تشغيل الأوامر، فحص الجهاز، تدريب النماذج عند توفر المتطلبات، وإنشاء المشاريع وتشغيلها واختبارها وإصلاح أخطائها.

لذلك NEXUS يعتبر:

**General-purpose digital execution system.**

---

# 4. المبادئ المعمارية

## 4.1 Goal-first

الهدف النهائي أهم من تنفيذ سلسلة ثابتة من الخطوات.

## 4.2 Prompt priority

التعليمات الحالية الصريحة أعلى أولوية من أي ذاكرة أو تفضيل سابق.

الترتيب:

```text
Current Prompt
>
Current Task Constraints
>
Workspace Policy
>
Project Decisions
>
User Preferences
>
Long-term Learning
```

## 4.3 Task-scoped full capability

NEXUS يمتلك قدرات واسعة، لكنه لا يستخدمها عشوائيًا.

القدرة مرتبطة بالمهمة.

## 4.4 Verification-first

إعلان النجاح يتطلب تحققًا فعليًا.

## 4.5 Persistence-first

المهمة لا تعتمد على بقاء نافذة التطبيق مفتوحة.

## 4.6 Local-first

البيانات الأساسية والنماذج والذاكرة وحالة المهمة محلية.

## 4.7 Model-agnostic

NEXUS لا يجب أن يعتمد على نموذج محدد.

## 4.8 Composable

كل Agent وTool وModel وSkill وPlugin يدخل من خلال عقد واضحة.

## 4.9 Graceful degradation

عند نقص الموارد، ينخفض الأداء أو يقل التوازي بدل خسارة المهمة.

---

# 5. ما هو خارج نطاق NEXUS

NEXUS ليس:

- نظام تشغيل بديلًا عن Windows.
- منصة لعب آلي.
- أداة للتحايل على أنظمة الحماية.
- مجرد واجهة للنموذج.
- مجرد Browser automation.
- مجرد IDE.
- مجرد RAG.
- مجرد remote desktop.

الـComputer Use يمكنه إدارة التطبيقات والألعاب والإعدادات حسب المهمة، لكن لا يُصمم لتجاوز Anti-cheat أو تنفيذ اللعب بدل المستخدم في الألعاب التي تمنع هذا النوع من الأتمتة.

---

# 6. تجربة المستخدم الأساسية

عند تشغيل NEXUS:

```text
┌─────────────────────────────────────────┐
│ NEXUS                          ● Ready  │
├──────────────┬──────────────────────────┤
│ Conversations│                          │
│              │        New Chat           │
│ Project A    │                          │
│ Project B    │   "شو بدك أعمل؟"          │
│ Task C       │                          │
│              │                          │
│              │ [Full Stack] [Android]   │
│              │ [Research] [Coding]      │
│              │ [Automation] [Computer]  │
│              │                          │
│              │ 🎙 + Attach               │
├──────────────┴──────────────────────────┤
│ > اكتب المهمة...                        │
└─────────────────────────────────────────┘
```

---

# 7. Capability Profiles

الاقتراحات الظاهرة في الشاشة ليست Modes مغلقة.

هي:

**Capability Profiles**

مثال:

### Full Stack

تفعّل:

- Web research
- frontend
- backend
- DB
- API
- testing
- Git
- deployment tooling

### Android

تفعّل:

- Android tooling
- Gradle
- emulator
- Android project indexing
- mobile-specific testing

### Research

تفعّل:

- web search
- source comparison
- document retrieval
- citations
- evidence memory

### Computer

تفعّل:

- screen
- windows
- keyboard
- mouse
- UI Automation
- application control

### Coding

تفعّل:

- repository indexing
- code agents
- terminal
- tests
- Git

أما المحادثة العامة، فـNEXUS يعطي الـOrchestrator جميع القدرات المتاحة ويترك القرار للنظام.

---

# 8. اللغة

NEXUS يجب أن يفهم:

- العربية.
- الإنجليزية.
- العربي + الإنجليزي في نفس الجملة.
- المصطلحات التقنية.
- أسماء الأدوات والمشاريع.
- الأوامر العامية.

مثال:

> "افتحلي Word، اعمل التقرير، جيب الصور من النت وحط references."

يجب أن يعتبر هذا Intent واحدًا.

---

# 9. الصوت

الصوت جزء أساسي من واجهة الإدخال.

Pipeline:

```text
Microphone
   ↓
Speech Capture
   ↓
Voice Activity Detection
   ↓
Speech-to-Text
   ↓
Language Detection
   ↓
Arabic/English Normalization
   ↓
NEXUS Prompt
```

المحرك يجب أن يعمل محليًا عند الإمكان. `sherpa-onnx` مثلًا مصمم للتعرف على الكلام محليًا دون الحاجة للإنترنت، ويدعم Windows إضافة إلى منصات أخرى.

اختيار النموذج الصوتي النهائي يجب أن يخضع لاختبار فعلي على جهاز NEXUS، خصوصًا مع i7-3770 وAVX-only.

---

# 10. تشغيل NEXUS مع Windows

NEXUS يبدأ مع Windows، لكنه لا يظهر كنافذة ضخمة.

التصميم:

```text
Windows
   ↓
NEXUS Launcher/Tray
   ↓
NEXUS Core Service
   ↓
Workers
```

الـTray مسؤول عن:

- فتح الواجهة.
- حالة النظام.
- المهام.
- Pause/Resume.
- Recovery notification.
- Notifications.

والـAI نفسه لا يجب أن يكون مربوطًا بالـTray.

---

# 11. Process Architecture

التقسيم المنطقي:

```text
NEXUS Launcher
       │
       ├── Desktop UI
       ├── NEXUS Core Service
       ├── Agent Workers
       ├── Model Runtime Manager
       ├── Computer Runtime
       ├── Browser Runtime
       ├── Persistence
       └── Remote Gateway
```

هذه ليست إلزامًا Processes منفصلة دائمًا؛ القرار النهائي يكون حسب الموارد والاستقرار.

---

# 12. NEXUS Core Service

المسؤول عن:

- Task Manager.
- Session Manager.
- Orchestrator.
- Agent Registry.
- Tool Registry.
- Scope.
- Permissions.
- Event Bus.
- Memory coordination.
- Model coordination.
- Recovery.
- Resource Manager.

ويستمر بالخلفية بعد إغلاق الواجهة.

---

# 13. Master Agent

Master Agent هو الوكيل الوحيد الذي يظهر للمستخدم كـ"العقل الرئيسي".

وظيفته:

```text
Understand
↓
Decide
↓
Delegate
↓
Monitor
↓
Integrate
↓
Verify
↓
Report
```

لا يجب أن يقوم بكل الأدوات بنفسه.

هو المدير.

---

# 14. Agent Runtime

الـAgent Runtime هو آلة تنفيذ الهدف:

```text
Observe
↓
Plan / Re-plan
↓
Select Agent / Tool
↓
Execute
↓
Observe Result
↓
Verify
↓
Save State
↓
Continue
```

ولا تكون المهمة:

```text
prompt → answer → done
```

---

# 15. Task State Machine

الحالة الرسمية:

```text
CREATED
  ↓
ANALYZING
  ↓
CLARIFICATION_REQUIRED
  ↓
PLANNING
  ↓
EXECUTING
  ↓
VERIFYING
  ↓
REPAIRING
  ↓
EXECUTING
  ↓
COMPLETED
```

مع حالات جانبية:

```text
PAUSED
RECOVERING
CANCELLED
WAITING_NETWORK
WAITING_RESOURCE
```

`FAILED` لا يعني مباشرة أن المهمة انتهت؛ يجب أولًا استنفاد recovery/repair paths المناسبة.

---

# 16. Input Processing

كل رسالة تمر بالمراحل:

```text
Raw Input
 ↓
Normalization
 ↓
Intent Extraction
 ↓
Requirement Extraction
 ↓
Task Classification
 ↓
Scope Detection
 ↓
Dependency Detection
 ↓
Clarification Gate
```

يستخرج:

- الهدف.
- المدخلات.
- الناتج.
- القيود.
- الموقع.
- التطبيقات.
- الإنترنت.
- المدة.
- التوازي.
- الأدوات.
- النطاق.

---

# 17. Clarification Gate

إذا المهمة كاملة:

> لا يسأل.

إذا هناك نقص شكلي:

> لا يسأل.

إذا هناك نقص جوهري يمنع التنفيذ:

> يسأل قبل بدء المهمة الطويلة.

مثال:

> "اعمل لي تطبيقًا وأرسل الإصدار النهائي."

إذا لا يوجد أي تعريف لماهية التطبيق:

> يطلب توضيحًا.

لكن بعد بداية المهمة لا يعود يسأل عن معلومة كان يمكن استنتاجها أو جمعها.

---

# 18. Scope Engine

هذه الطبقة جوهرية.

مثال:

```text
Task:
Build Client Website

Scope:
M:\ClientWebsite\

Allowed:
Files
Terminal
Browser
Git
GitHub
VS Code

Objective:
Complete website
```

NEXUS يملك القدرة على بقية الجهاز، لكن **لا يستخدمها لأنها خارج علاقة المهمة**.

---

# 19. Scope ليس Sandbox

NEXUS لا يفترض أن M:\ClientWebsite معزول تقنيًا عن باقي Windows.

الـScope هو:

> **حدود العمل المنطقية والسياساتية للمهمة.**

لكن بعض المهام قد تحتاج:

- Chrome.
- Windows Settings.
- Word.
- GitHub.
- Blender.

لذلك الـScope يتضمن أيضًا الموارد التشغيلية غير الملفية.

---

# 20. Workspace System

كل Workspace مستقل:

```text
Workspace
├── Path
├── Tasks
├── Conversations
├── Memory
├── Git state
├── Code index
├── Skills
├── Decisions
└── History
```

مثال:

```text
Workspace A = NEXUS
Workspace B = Client 1
Workspace C = Android Project
```

---

# 21. Cross-Workspace Access

الوصول ممكن عند طلب المهمة.

مثال:

> "استعمل قرار المصادقة الموجود في Workspace A."

النظام:

```text
Task B
 ↓
Memory request
 ↓
Workspace A
 ↓
Retrieve relevant knowledge
 ↓
Return only needed information
```

ولا يتم خلط التاريخ بين Workspaces.

---

# 22. Workspace Memory

كل Workspace يملك Namespace مستقلًا للذاكرة.

لكن هناك Memory Global اختيارية.

البنية:

```text
GLOBAL
│
├── USER
│
├── PROJECT
│
├── WORKSPACE
│
├── TASK
│
├── SESSION
│
└── AGENT
```

---

# 23. Memory Engine

الذاكرة لا تحفظ "المحادثة" فقط.

تحفظ:

- facts
- preferences
- decisions
- observations
- lessons
- errors
- successful approaches
- skills
- project state
- source evidence

---

# 24. Memory Priority

```text
Current Prompt
>
Current Task
>
Workspace
>
Project
>
User
>
Learned Knowledge
```

أهم شيء:

> الذاكرة القديمة لا تقهر التعليمات الجديدة.

---

# 25. Memory Types

يجب أن يكون لكل Memory نوع:

### Fact
معلومة مؤكدة.

### Decision
قرار تم اتخاذه.

### Observation
شيء لاحظه النظام.

### Hypothesis
تفسير مؤقت.

### Lesson
درس مستخلص من التجربة.

### Skill
طريقة تشغيل قابلة لإعادة الاستخدام.

### Evidence
معلومة مرتبطة بمصدر.

---

# 26. Confidence

كل Memory يجب أن تحمل:

```text
confidence
source
created_at
updated_at
scope
```

حتى لا يتحول التخمين إلى حقيقة دائمة.

---

# 27. Structured Storage

SQLite:

```text
tasks
sessions
events
agents
tools
models
workspaces
permissions
checkpoints
settings
hardware_profile
```

SQLite مناسبة لأنها قاعدة محلية embedded وبدون خادم منفصل.

---

# 28. Semantic Storage

الـsemantic memory والـcode retrieval يمكن أن تستخدم Vector DB.

**Qdrant** مرشح قوي هنا؛ المشروع مفتوح المصدر ومصمم للـvector search/filtering والـsemantic retrieval. 

لكن:

> Qdrant ليس "عقل الذاكرة".

NEXUS Memory Manager هو الذي يحدد معنى الذاكرة.

---

# 29. Mem0

Mem0 مرشح لطبقة persistent memory.

المشروع يعرّف طبقات Conversation/Session/User memory ويوفر APIs للبحث والحفظ المرتبطين بهوية/session.

لكن:

> سنبني NEXUS Memory abstraction فوقه.

حتى نستطيع تغيير backend لاحقًا.

---

# 30. Learning Engine

التعلم هو طبقة مستقلة عن Memory.

```text
Experience
 ↓
Extract Candidate
 ↓
Validate
 ↓
Confidence
 ↓
Store
 ↓
Reuse
```

مصادر التعلم:

- المحادثات.
- المهام.
- الأخطاء.
- النجاحات.
- البحث.
- استخدام الأدوات.
- المهارات.
- استشارات AI الخارجية.

---

# 31. Self-Improvement

المستويات:

```text
Memory
↓
Skills
↓
Workflow Optimization
↓
Prompt Optimization
↓
Model Optimization
↓
Fine-tuning
```

وليس من الضروري أن يصل NEXUS لكل مستوى من اليوم الأول.

---

# 32. Learning Chat

يُدعم نوع محادثة مخصص:

> Learning Session

مثل:

> "ادرس هذا الموضوع."

فيستطيع NEXUS:

```text
Research
↓
Talk to external AI
↓
Compare
↓
Extract knowledge
↓
Test knowledge
↓
Create lesson/skill
↓
Store
```

---

# 33. التعلم من AI خارجي

إذا كانت قدرة النموذج المحلي غير كافية:

```text
Local reasoning
↓
Search
↓
Documentation
↓
External AI Consultation
↓
Cross-check
↓
Evidence
↓
Use
```

الـAI الخارجي مصدر معرفة، وليس مرجعًا مطلقًا.

---

# 34. Prompt / Workflow Self-Optimization

NEXUS يمكنه اكتشاف:

> "هذه الطريقة تسبب 4 محاولات بدل 2."

فيقترح أو يختبر Workflow أفضل.

التغيير يمر:

```text
Candidate
↓
Test
↓
Compare
↓
Accept
```

لا تعديل مباشر غير مقيد.

---

# 35. Fine-Tuning

Fine-tuning جزء مستقبلي من Learning Engine وليس شرطًا لكل التعلم.

الشروط:

- Dataset مناسب.
- قياس قبل/بعد.
- حماية من regression.
- إمكانية rollback.
- حفظ النموذج السابق.

---

# 36. Agent Registry

كل Agent يملك Manifest:

```text
Agent
├── id
├── role
├── description
├── model policy
├── tools
├── skills
├── permissions
├── context requirements
├── input schema
├── output schema
└── verification rules
```

---

# 37. Agent Types

النظام لا يكون محدودًا بخمسة Agents.

الأنواع الأساسية:

```text
Master
Planner
Researcher
Analyst
Architect
Coder
Frontend
Backend
Database
DevOps
Browser
Computer
Windows
Documents
Tester
Debugger
Security
Performance
Reviewer
Git
Recovery
Learning
```

ويمكن إضافة Agents مستقبلية.

---

# 38. Multi-Agent Scheduling

Master يقرر:

### Sequential

عندما الخطوات تعتمد على بعضها.

### Parallel

عندما يمكن تنفيذها مستقلًا.

مثال:

```text
Research API
       \
        → Architecture
Database/
       /
Frontend Research
```

---

# 39. Agent Ownership

لمنع التصادم:

```text
Agent A
owns auth/
```

Agent B يحتاج تعديل auth:

```text
Request
↓
Resource Manager
↓
Coordinate
```

ولا نترك Agentين يكتبان نفس الملفات عشوائيًا.

---

# 40. Agent Communication

يجب أن تكون الاتصالات structured:

```text
AgentMessage
├── task_id
├── sender
├── receiver
├── message_type
├── status
├── evidence
├── confidence
├── data
└── timestamp
```

---

# 41. Agent Harness

الـHarness هو الطبقة التي تعطي الـModel:

- Context.
- Tools.
- Memory.
- Task state.
- Rules.
- Skills.
- Observations.

ويعيد:

- Action.
- Tool call.
- Delegation.
- Decision.

---

# 42. ECC

ECC هو أحد أهم المراجع/المصادر التي وجدناها.

الحالة الحالية للمستودع توضح وجود agents وskills وcommands وhooks وrules وmemory وECC 2.0، مع بقاء ECC 2.0 في حالة alpha وفق توثيق المشروع الحالي.

سنستفيد منه في:

- Skill organization.
- Rules.
- Hooks.
- Agent patterns.
- Verification.
- Learning concepts.
- Security ideas.

لكن لا يمتلك:

- NEXUS Task Model.
- Scope.
- Global runtime.
- Windows architecture.
- NEXUS identity.

---

# 43. Cline Architecture

Cline يقدم فصلًا ممتازًا بين:

```text
shared
llms
agents
core
host apps
```

والـSDK الحالي يصف:

- Agent runtime.
- Tools.
- Hooks.
- Extensions.
- Teams.
- Streaming.
- Stateful Core.
- Session lifecycle.
- Storage.
- Local/hub/remote runtimes.

كما أن SDK قابل للاستخدام كـlibrary داخل تطبيق آخر.

قرار NEXUS:

> **Reference + Adapt.**

---

# 44. LangGraph

LangGraph مناسب للـstateful orchestration وlong-running workflows، وله persistence/checkpoint concepts قوية، وهو حاليًا نشط وله أكثر من 37k Star و553 release حتى الفحص الحالي.

قرار NEXUS:

> **Use/Adapt كمرشح لـOrchestration layer.**

---

# 45. Prime Agent

Prime Agent مهم جدًا بالنسبة لفكرة التعلم الطويل.

المشروع الحالي مبني على:

- persistent REPL.
- recursive subagents.
- continual harness.
- durable state.
- memories.
- skills.
- reusable subagent specifications.
- heartbeats.
- autonomous mode.
- resume/background sessions.

والأهم أنه صريح جدًا في التفريق بين الـRLM runtime والـContinual Harness.

لكن يوجد Issue مفتوح في أغسطس 2026 حول مشكلة وصول بعض حالات الـcontinual harness، لذلك لا نعامل المشروع كمرجع "مضمون بلا عيوب".

قرار NEXUS:

> **Research/Reference قوي جدًا.**

---

# 46. OpenHands

OpenHands من أقوى مشاريع AI-driven development، والـcore وagent-server الأساسيان MIT، مع استثناء enterprise directory الذي له ترخيص مختلف. الصفحة الحالية تعرض أكثر من 68k Star.

قرار NEXUS:

> Coding Agent reference/component candidate.

---

# 47. OpenCode

OpenCode حاليًا من أكبر المشاريع في هذه الفئة، والصفحة الحالية تعرض أكثر من 200k Star وMIT، وهو coding agent مفتوح المصدر وله general subagent للبحث والمهام متعددة الخطوات.

قرار NEXUS:

> Reference قوي للـcoding UX/runtime، وليس Core NEXUS بالكامل.

---

# 48. Aider

Aider من أهم المراجع لمشروعنا بسبب **Repository Map**.

المشروع يبني خريطة مختصرة للمستودع تحتوي أهم الملفات والرموز والتواقيع، ويرسلها مع طلبات التعديل حتى يفهم LLM العلاقات في المشروع دون تحميل كامل المستودع إلى الـcontext.

قرار NEXUS:

> **Reference/Adapt لـCodebase Intelligence.**

---

# 49. Large Codebase Architecture

للمشاريع التي فيها 300k أو 400k سطر:

```text
Repository
↓
File Scanner
↓
Tree-sitter / parser
↓
Symbol index
↓
Dependency graph
↓
API graph
↓
Test map
↓
Repo map
↓
Semantic retrieval
↓
Relevant context
↓
Agent
```

لا نرسل 400k سطر إلى النموذج.

---

# 50. Tree-sitter

Tree-sitter parser generator وincremental parsing library، مصمم ليكون سريعًا حتى أثناء التحرير، robust مع syntax errors، وruntime الخاص به C ويمكن تضمينه في التطبيقات. الصفحة الحالية تعرض 25.6k Star و99 إصدارًا.

قرار NEXUS:

> **Use.**

---

# 51. Browser Architecture

NEXUS لا يتعامل مع المتصفح بطريقة واحدة.

نستخدم طبقات:

```text
HTTP/API
↓
Browser Automation
↓
DOM / Accessibility
↓
Vision
↓
Computer Input
```

ويختار الـOrchestrator المستوى المناسب.

---

# 52. Browser Use

Browser Use من أقوى المرشحين؛ الصفحة الحالية تعرض نحو 98.8k Star و129 release، ويقدم browser-oriented agents وأدوات persistent، مع إمكانية استخدام local models.

قرار NEXUS:

> **Use/Adapt.**

---

# 53. Browser Harness

Browser Harness يصف نفسه كـthin editable CDP harness يتصل مباشرة بالـChrome، ويوفر self-healing behavior ويتيح للـAgent إنشاء helpers عند اكتشاف capability ناقصة.

قرار NEXUS:

> **Adapt/Reference.**

---

# 54. Playwright

Playwright هو execution layer للمتصفح، وليس Agent.

يدعم Chromium وFirefox وWebKit، وهو مناسب جدًا لتوفير أفعال browser قابلة للضبط والتحقق.

قرار NEXUS:

> **Use.**

---

# 55. Browser Session Architecture

يجب أن يدعم NEXUS:

```text
User Browser Session
Agent Browser Session
```

بحيث يستطيع:

- المستخدم العمل في Chrome.
- NEXUS العمل في Session أخرى.

ولا تختلط الـCookies والسياقات إلا عند الحاجة الصريحة.

---

# 56. Windows Computer Runtime

Computer Runtime يجب أن يدعم:

```text
Screen
Windows
Mouse
Keyboard
Clipboard
UI Automation
Processes
Applications
```

---

# 57. Windows Harness

`browser-use/windows-harness` أصبح مرشحًا مهمًا جدًا؛ المستودع الحالي يجمع Windows UI Automation، screenshots، mouse/keyboard، browser، Python، PowerShell وfilesystem، ويحتوي اختبارات وملف SECURITY، وهو متوافق مع Windows 10/11 بحسب المشروع. لكنه ما زال مصنّفًا كـexperimental.

قرار NEXUS:

> **Adapt behind a NEXUS Computer API.**

أي لا نربط Core مباشرة بواجهاته.

---

# 58. pywinauto

pywinauto يوفر Windows GUI automation، ويدعم Win32 وMS UI Automation، والتعامل مع الواجهات وعناصر التحكم والمدخلات.

قرار NEXUS:

> **Use as one Windows-control backend.**

وليس backend الوحيد.

---

# 59. Windows Control Hierarchy

NEXUS يحاول:

```text
1. Native/Application API
2. Windows UI Automation
3. Browser/DOM Automation
4. Vision
5. Mouse/Keyboard
```

كل مستوى أعلى في الاعتمادية أو البنية يستخدم عندما يكون متاحًا، والطبقات الأدنى تكون fallback.

---

# 60. Window Manager

كل نافذة يديرها NEXUS تحصل على:

```text
Window ID
Application
Workspace
Task
Agent Owner
Position
Size
Visibility
Input ownership
```

---

# 61. Human + AI Parallel Usage

هذه ميزة أساسية عندك.

مثال:

```text
Monitor 1:
War Thunder → USER

Monitor 2:
Chrome → NEXUS
```

أو:

```text
Chrome A → USER
Chrome B → NEXUS
```

أو:

```text
PowerPoint → NEXUS
VS Code → NEXUS
Browser → USER
```

حسب الهدف.

---

# 62. Input Arbitration

NEXUS يجب أن يتعامل مع:

```text
Human Input
AI Input
```

ليس بمنطق "كل حركة ماوس للمستخدم توقف Agent".

بل بمنطق:

> **Window/Input ownership**

فإذا كان AI يعمل في نافذة مملوكة للمهمة، لا يختلط عمل المستخدم عليها.

---

# 63. Overlay

عندما يستخدم Computer Control:

```text
┌────────────────────────┐
│ NEXUS is working       │
│ [Pause] [Resume]       │
└────────────────────────┘
```

شفافة في زاوية الشاشة.

ويظل مؤشر NEXUS مرئيًا حسب نوع التحكم المستخدم.

---

# 64. Computer Vision

Vision تستخدم لـ:

- فهم الشاشة.
- اكتشاف العناصر.
- قراءة layout.
- فهم التصميم.
- مراقبة النتائج.
- حالات لا توفر Accessibility Tree مفيدة.

لكن Vision ليست الحل الوحيد.

---

# 65. Screenshots

لا نأخذ Screenshot لكل خطوة لمجرد الحفظ.

نأخذها:

- عند الحاجة للفهم.
- عند التحقق.
- عند وجود تغيير مهم.
- عند فشل.
- عند طلب المستخدم.
- عندما يحتاج Agent تذكر الحالة البصرية.

---

# 66. War Thunder Use Case

المثال الرسمي في NEXUS:

```text
User:
حلل مواصفات جهازي واضبط War Thunder.

NEXUS:
↓
Hardware Profile
↓
Launch/Focus Game
↓
Observe UI
↓
Adjust settings
↓
Apply
↓
Observe live behavior
↓
User tests/plays
↓
NEXUS monitors permitted visual/performance signals
↓
Report
↓
Recommend changes
```

NEXUS لا يهدف إلى لعب المباراة بدل المستخدم أو تجاوز أنظمة اللعبة.

---

# 67. Application Control

ينطبق المبدأ نفسه على:

- Word.
- PowerPoint.
- Blender.
- AutoCAD.
- VS Code.
- Browsers.
- Windows Settings.
- أدوات التطوير.
- تطبيقات Electron.
- برامج أخرى.

---

# 68. Word Task

مثال:

```text
"اكتب تقريرًا في Word عن Smart Buildings.
ابحث عن المصادر.
اجلب الصور.
نسّق التقرير.
راجعه.
احفظه."
```

المسار:

```text
Understand
↓
Research
↓
Source collection
↓
Document creation
↓
Word control
↓
Insert content
↓
Formatting
↓
Review
↓
Save
↓
Verify
```

---

# 69. PowerPoint Task

```text
Research
↓
Outline
↓
Slides
↓
Images
↓
Sources
↓
PowerPoint
↓
Formatting
↓
Visual review
↓
Save
↓
Openability check
```

---

# 70. Documents

Docling مرشح قوي جدًا كـdocument ingestion layer؛ يدعم PDF وDOCX وPPTX وXLSX وHTML وصور وصيغًا متعددة، ويمتلك representation موحدًا للمستندات، والـcodebase نفسه MIT مع ضرورة فحص تراخيص النماذج المنفصلة.

قرار NEXUS:

> **Use/Adapt.**

---

# 71. Research Engine

البحث ليس:

> "أول Google result."

بل:

```text
Query
↓
Search
↓
Collect
↓
Deduplicate
↓
Classify sources
↓
Compare
↓
Verify
↓
Extract evidence
↓
Store
```

---

# 72. Research Sources

يمكن أن يستخدم:

```text
Web
GitHub
Documentation
Forums
Academic sources
Local files
Knowledge base
External AI
```

حسب المهمة.

---

# 73. Source Evaluation

لكل نتيجة:

```text
Source
Type
Authority
Date
Relevance
Evidence
Confidence
```

وبالتالي يستطيع أن يقول:

> "هذا مصدر رسمي."

أو:

> "هذه تجربة مستخدم."

---

# 74. GitHub Discovery Engine

مثال:

> "جيبلي أفضل 5 repositories لبناء X."

المسار:

```text
GitHub Search
↓
Candidates
↓
Filter
↓
Activity
↓
License
↓
Architecture
↓
Issues
↓
Documentation
↓
Compatibility
↓
Ranking
```

---

# 75. External AI Consultation

إذا المهمة تحتاج معرفة أعلى من قدرة النموذج المحلي:

```text
NEXUS
↓
Need expertise
↓
Search
↓
Potential external AI
↓
Consult
↓
Extract
↓
Cross-check
↓
Continue
```

ولا تصبح كل إجابة خارجية Memory دائمة تلقائيًا.

---

# 76. Tool System

كل قدرة قابلة للتنفيذ تصبح Tool:

```text
Tool Registry
```

ويحمل:

```text
name
description
input_schema
output_schema
permissions
risk
scope
availability
version
verification
```

---

# 77. Tool Router

المسار:

```text
Agent
↓
Tool Router
↓
Capability Discovery
↓
Permission
↓
Scope
↓
Resource Check
↓
Execute
↓
Normalize Result
↓
Verify
```

---

# 78. Native Tools

الـNative Tools مناسبة للأشياء المرتبطة مباشرة بالنظام:

```text
Filesystem
Terminal
Windows
Process
Hardware
Input
Clipboard
Model runtime
Task state
Workspace
```

---

# 79. MCP

MCP يصبح طبقة interoperability.

الـMCP الرسمي يحدد SDKs لبناء clients وservers؛ الـPython SDK الحالي هو v2 stable line، ويدعم stdio وStreamable HTTP وSSE، بينما TypeScript SDK الحالي v2 يطبق مواصفة 2026-07-28.

قرار NEXUS:

> **Use MCP، لكن خلف NEXUS Tool Router.**

---

# 80. لماذا لا نعطي MCP حرية مباشرة؟

لأن MCP Tool قد يملك:

- filesystem
- Git
- web
- external services

لذلك:

```text
MCP Tool
↓
NEXUS Policy
↓
Scope
↓
Permission
↓
Execute
```

---

# 81. Plugin System

NEXUS يدعم:

```text
Plugins
├── Agents
├── Tools
├── Skills
├── Models
├── MCP servers
├── Integrations
└── UI extensions
```

ويتم اكتشاف الإضافات وتسجيلها دون تغيير Core.

---

# 82. Skill System

Skill هي:

> Capability/workflow قابل لإعادة الاستخدام.

مثال:

```text
Create_SaaS_Project
Research_GitHub
Build_PowerPoint
Analyze_Windows_App
Optimize_App_Settings
```

كل Skill:

```text
Description
Inputs
Tools
Workflow
Verification
Version
```

---

# 83. Skill Creation

NEXUS يمكنه:

```text
Observe repeated workflow
↓
Extract candidate
↓
Create Skill
↓
Test
↓
Verify
↓
Register
```

---

# 84. Skill Learning

إذا أعطيته نفس المهمة عدة مرات:

> يمكن أن يستنتج طريقة قابلة لإعادة الاستخدام.

لكن لا يتم تحويل كل تجربة إلى Skill.

يجب أن تكون:

- متكررة.
- مفيدة.
- قابلة للتحقق.
- غير مرتبطة خطأً بمعلومة مؤقتة.

---

# 85. Model Manager

NEXUS لا يرتبط بنموذج واحد.

البنية:

```text
Model Manager
├── Registry
├── Loader
├── Unloader
├── Router
├── Benchmark
├── Health
└── Resource integration
```

---

# 86. Model Pool

قد يحتوي:

```text
Tiny
Small
Coder
Long Context
Vision
Speech
```

لكن ليس شرطًا تحميلها كلها.

---

# 87. Dynamic Model Loading

القاعدة:

```text
Task
↓
Capability requirement
↓
Available models
↓
RAM/VRAM
↓
Current load
↓
Select
↓
Load
↓
Use
↓
Unload/Keep warm
```

---

# 88. نتائج MiMo Edge

اختباراتك الفعلية أعطتنا baseline قوي:

- Qwen2.5-Coder-1.5B: تقريبًا 9.57 tok/s عند ctx=8192.
- LFM2.5-1.2B: تقريبًا 7.54 tok/s عند ctx=8192.
- Qwen3-0.6B مع KV-Q4: نحو 11.66 tok/s في القياس المقاس.
- DS-Coder-1.3B مع GPU: نحو 29.14 tok/s في الاختبار المقاس.
- KV Q4 قلل KV memory في الاختبار بنحو 4x مع تحسن في tg.
- Flash Attention لم يكن مناسبًا لبيئة AVX-only التي اختبرتها.
- ngram/router flags التي اختبرتها لم تكن مدعومة في build المستخدم.

هذه الأرقام **نتائج بيئة الاختبار التي زودتني بها أنت**، وليست مواصفات عامة لأي جهاز آخر.

---

# 89. NEXUS Hardware Profile

عند التثبيت/أول تشغيل:

```text
CPU
GPU
VRAM
RAM
Storage
Displays
Resolution
Windows version
Network
Devices
Installed software
```

وتحفظ في قاعدة NEXUS.

---

# 90. Hardware Monitoring

يُراقب:

```text
CPU
RAM
GPU
VRAM
Disk
Processes
Temperature where available
```

وعند التغير:

```text
Hardware change
↓
Reprofile
↓
Update Model Manager
↓
Update Resource Manager
```

---

# 91. Resource Manager

يحدد:

```text
How many agents?
How many models?
Which model?
Which tools?
How much parallelism?
```

ويتأكد من ألا ينهار الجهاز بسبب مهمة واحدة.

---

# 92. Resource Degradation

إذا الذاكرة انخفضت:

```text
Reduce concurrency
↓
Unload idle model
↓
Switch smaller model
↓
Reduce unnecessary context
↓
Continue
```

المبدأ:

> **البطء أفضل من ضياع المهمة.**

---

# 93. Local Model Runtime

`llama.cpp` هو المرشح الأساسي الحالي.

المشروع مفتوح المصدر، ويدعم local inference/server، وقد تم استخدامه أصلًا في اختبارات MiMo Edge الخاصة بك.

قرار NEXUS:

> **Use as primary local inference backend.**

لكن Model Manager يبقى مستقلًا عنه.

---

# 94. LocalAI

LocalAI يبقى مرجعًا اختياريًا لفكرة composable backends، لأنه يجمع LLM/Vision/Voice/MCP وغيرها عبر backends متعددة، لكن لا أجعله Core على جهازك الحالي.

---

# 95. Agent Context Builder

قبل كل Model Call:

```text
Current Prompt
+
Task State
+
Relevant Memory
+
Workspace
+
Project Knowledge
+
Agent Role
+
Available Tools
+
Current Observation
+
Recent Tool Results
```

ثم:

```text
Context pruning
↓
Budget
↓
Model
```

---

# 96. Context Compaction

عندما تصبح المحادثة أو المهمة طويلة:

```text
Recent critical context
+
Task summary
+
Persistent state
+
Relevant memories
+
Current plan
```

ولا نعتمد على history الخام كله.

---

# 97. Conversation Persistence

المحادثة لا تنتهي معرفيًا عند إغلاق النافذة.

كل Conversation:

```text
ID
Messages
Attachments
Task links
Workspace
Memory
Models
Activity
```

والـNEXUS identity تبقى مستقلة عن Conversation.

---

# 98. Conversation ≠ Agent Identity

ممكن:

```text
Conversation A
Conversation B
Conversation C
```

لكنها جميعًا تتعامل مع:

> نفس NEXUS identity

مع اختلاف:

- Session context.
- Workspace context.
- Task context.

وهذا يتناسب مع فلسفة persistent agent identity التي نراها في مشاريع مثل Letta/Prime، دون أن نربط NEXUS بأحدهما بالكامل.

---

# 99. Task History

كل مهمة تحتفظ بـ:

```text
Original Prompt
Clarifications
Plan
Agents
Tools
Events
Errors
Repairs
Checkpoints
Result
Lessons
```

---

# 100. Event Bus

كل شيء ينتج أحداثًا:

```text
task.created
task.started
plan.created
agent.started
agent.completed
tool.called
tool.completed
window.opened
model.loaded
checkpoint.created
test.failed
repair.started
task.recovered
task.completed
```

الجهات التي تستخدمها:

```text
Desktop UI
Logger
Recovery
Remote Web
Notifications
Analytics
```

---

# 101. Activity Timeline

في الشات:

```text
✓ Task understood

→ Planner
  creating architecture

→ Research Agent
  searching documentation

→ GitHub
  analyzing repositories

→ Coder
  modifying auth module

→ Tester
  running tests

✗ 2 tests failed

→ Debugger
  investigating

✓ Fixed

→ Reviewer
  final verification
```

هذا هو **execution trace** الذي ترى من خلاله ماذا فعل النظام فعليًا.

---

# 102. Chain of Thought

الواجهة لا تعرض السلسلة الداخلية الخام للتفكير.

بدلًا منها تعرض:

- ما المهمة الحالية.
- ما القرار التنفيذي.
- ما الأداة المستخدمة.
- ما النتيجة.
- ما الذي فشل.
- كيف تمت المعالجة.
- ما الخطوة التالية.

وهذا يوفر شفافية عملية حقيقية بدون تحويل الواجهة إلى تفريغ غير منضبط لتفكير النموذج الداخلي.

---

# 103. Verification Engine

لا يوجد:

```text
Agent says Done
→ Done
```

بل:

```text
Agent
↓
Verifier
↓
Evidence
↓
Pass / Repair
```

---

# 104. Software Verification

حسب المشروع:

```text
Build
Unit tests
Integration tests
E2E tests
Lint
Type checks
Security
Performance
Packaging
Deployment validation
```

---

# 105. Browser Verification

```text
URL
DOM
Accessibility
Expected state
Downloaded file
Upload result
Content
```

---

# 106. Windows Verification

```text
Window exists
Application state
UI state
Process state
Output file
Expected result
```

---

# 107. Document Verification

```text
Content
Structure
Formatting
References
Images
Openability
Page/slide count
```

---

# 108. Research Verification

```text
Source quality
Source date
Cross-check
Contradictions
Evidence
Confidence
```

---

# 109. Repair Loop

عند فشل التحقق:

```text
Failure
↓
Diagnose
↓
Find root cause
↓
Search if needed
↓
Try solution A
↓
Verify
↓
Try B if required
↓
Verify
↓
Continue
```

لا يتم التخلي عن الخطة بسبب فشل محاولة واحدة.

---

# 110. Heartbeat

Health Monitor يتابع:

- هل الـworker حي؟
- هل الـprocess موجود؟
- هل تتغير الحالة؟
- هل هناك أفعال متكررة بلا تقدم؟
- هل tool ينتج نتيجة؟
- هل agent عالق؟
- هل الموارد طبيعية؟

---

# 111. Stall Detection

إذا:

```text
same action
same state
same error
```

بشكل متكرر:

```text
Potential stall
↓
Diagnose
↓
Re-plan
↓
Recover
```

---

# 112. Tool Timeout

حسب قرارك:

> لا نضع timeout غبيًا يقتل أداة لأنها احتاجت وقتًا.

بدل ذلك:

### Tool Health

يتم تحديد timeout فقط إذا كانت طبيعة الـTool تحتاج ذلك، أو إذا كانت هناك دلائل فعلية على أنها stuck.

---

# 113. Task Time Policy

في بداية المهمة يمكن أن يكون:

```text
30 minutes
```

أو:

```text
Until goal completion
```

أو إعداد آخر.

هذا **Task deadline** وليس Tool timeout.

---

# 114. Long-running Task

المهمة يجب أن تستطيع العمل:

- دقائق.
- ساعات.
- أيام.

بحسب طبيعة المهمة.

ولا تعتبر:

> "أنشأت بعض الملفات"

نهاية.

---

# 115. Persistence

كل Task طويلة الأمد تعتمد على:

```text
Task State
+
Checkpoint
+
Workspace
+
Memory
+
Agent State
+
Git state
```

---

# 116. Checkpoint Manager

أنواع Checkpoints:

### State checkpoint
حالة التنفيذ.

### Task checkpoint
مرحلة المهمة.

### Project checkpoint
حالة المشروع.

### Git checkpoint
commit/branch state.

---

# 117. متى يأخذ Checkpoint؟

- بداية المهمة.
- نهاية Phase.
- قبل تغيير كبير.
- بعد تغيير كبير.
- بعد اختبار مهم.
- قبل عملية عالية المخاطر.
- على interval مناسب.

---

# 118. Restart Recovery

عند إقلاع Windows:

```text
NEXUS starts
↓
Find interrupted tasks
↓
Validate state
↓
Inspect real environment
↓
Prepare recovery summary
↓
Ask Resume or follow policy
```

---

# 119. Recovery لا يثق بالذاكرة وحدها

مثال:

```text
Memory says:
app.py created

Filesystem says:
app.py missing
```

الواقع:

> Filesystem wins.

لذلك recovery يجمع:

```text
Persisted state
+
Filesystem state
+
Process state
+
Git state
+
Application state
```

---

# 120. Resume

Resume يبدأ من:

> **آخر نقطة مؤكدة بعد reconciliation**

وليس من آخر جملة كتبها Agent.

---

# 121. Scoped Rollback

Rollback يكون حسب الوظيفة.

مثلاً:

> ارجع آخر تعديل للكود.

يشمل:

```text
Code
Files
Git
```

ولا يمس:

```text
Memory
Learning
Conversation
```

إلا في عملية rollback خاصة بها.

---

# 122. Git Architecture

Git manager:

```text
Repository
Branch
Worktree
Commit
Diff
Merge
Tag
Rollback
```

GitHub manager:

```text
Repository
Clone
Pull
Push
PR
Issue
Release
Search
```

---

# 123. Git Strategy

### Small change
Commit مباشر.

### Major feature
Branch.

### Parallel agents
Worktrees/isolated branches.

### Risky refactor
Checkpoint + branch.

### Release
Tests + review + tag/release بحسب المهمة.

---

# 124. GitHub Token

يحفظ محليًا عبر Secret abstraction.

ولا يظهر في:

- Chat.
- Memory.
- Activity.
- Tool output.
- Screenshots.

ويتعامل Agent معه كـcredential reference لا كنص عادي.

---

# 125. Repository Intelligence

عند Clone:

```text
Clone
↓
Detect stack
↓
Index files
↓
Parse symbols
↓
Build graph
↓
Run existing tests
↓
Understand architecture
↓
Create project map
```

---

# 126. Architecture Map

يحفظ:

```text
Modules
Components
Services
Dependencies
APIs
DB
Tests
Entry points
Configuration
```

وتتحدث تلقائيًا مع تغيّر المشروع.

---

# 127. Repository Map

نستخدم فكرة Aider:

```text
Files
+
Important symbols
+
Signatures
+
Relations
```

ثم نستخدمها لتقليل context.



---

# 128. Testing Agent

Agent خاص بالاختبارات يمكنه:

```text
Read test strategy
↓
Generate tests
↓
Run tests
↓
Analyze failures
↓
Repair
↓
Re-run
```

---

# 129. Security Agent

Agent متخصص يعمل مثل:

```text
Dependency scan
Secrets scan
Static analysis
Configuration checks
Permission review
```

Trivy مثلًا يوفر scanners للثغرات وmisconfigurations وsecrets وlicenses عبر filesystem وGit repository وغيرها.

قرار NEXUS:

> استخدام الأدوات الأمنية المتخصصة ضمن Verification، لا بناء Scanner ضخم من الصفر.

---

# 130. Code Quality

بحسب اللغة:

```text
Compiler
Linter
Type checker
Static analyzer
Security scanner
Tests
```

مثل Pyright للمشاريع Python.

---

# 131. Document Intelligence

Pipeline:

```text
Document
↓
Docling
↓
Structured representation
↓
Chunking
↓
Metadata
↓
Memory / Search
```

وDocling يدعم حاليًا PDF وDOCX وPPTX وXLSX وHTML وصورًا وصيغًا متعددة.

---

# 132. Offline Mode

عند غياب الإنترنت:

```text
Task
├── Local work
└── Network-dependent work
```

المحلي يستمر.

الجزء الذي يحتاج الشبكة:

```text
WAITING_NETWORK
```

وعند عودة الإنترنت:

```text
Resume blocked dependency
```

هذا مطابق للهدف الأصلي باستمرار العمل المحلي وعدم ضياع حالة المهمة عند انقطاع الاتصال.

---

# 133. External Connectivity

عند توفر الإنترنت يمكن NEXUS استخدام:

- Web.
- GitHub.
- APIs.
- External AI.
- Downloads.
- Documentation.
- Repositories.

لكن لا تصبح الشبكة شرطًا للـCore نفسه.

---

# 134. Model Availability

NEXUS يجب أن يملك:

```text
Model Registry
```

لكل نموذج:

```text
name
size
format
capabilities
context
RAM requirement
VRAM requirement
benchmark
status
```

---

# 135. Model Benchmark

عند إضافة نموذج جديد:

```text
Load
↓
Warm-up
↓
Prompt benchmark
↓
Generation benchmark
↓
Context benchmark
↓
Memory usage
↓
Stability
↓
Register profile
```

وبذلك Model Router يعتمد على نتائج الجهاز الحقيقي بدل التخمين.

---

# 136. Model Routing

مثال:

```text
Delete file
→ Fast tiny

General chat
→ Small general

Coding
→ Coder

Large project analysis
→ Long-context candidate

Image/screen
→ Vision

Speech
→ Speech model
```

والاختيار يعتمد أيضًا على:

```text
RAM
VRAM
current load
latency
```

---

# 137. Local Inference

`llama.cpp` هو backend الأساسي الحالي.

الـNEXUS Model Manager لا يعتمد عليه كواجهة مستخدم؛ يستخدم Adapter.

```text
NEXUS Model API
↓
llama.cpp Adapter
↓
llama-server
↓
GGUF model
```

وهذا يجعل تبديل runtime لاحقًا ممكنًا.

---

# 138. Tiny Model Philosophy

الفكرة ليست:

> "نجعل 1B يساوي 100B."

الهدف:

> نقل جزء كبير من القدرة من داخل النموذج إلى النظام حوله.

```text
Small Model
+
Tools
+
Memory
+
Planning
+
Agents
+
Retrieval
+
Computer
+
Verification
+
Recovery
```

وهذا قد يجعل النظام أكثر فاعلية بكثير في المهام المحددة، لكنه لا يعني أن النموذج نفسه أصبح مكافئًا رياضيًا لنموذج عملاق.

---

# 139. Computer Capability Discovery

عند المهمة:

> "عدّل إعدادات تطبيق X."

NEXUS يبحث:

```text
Can API do it?
↓
Can UI Automation?
↓
Can Browser?
↓
Can Vision?
↓
Can Input?
```

ويختار أقل طبقة مناسبة.

---

# 140. Application Discovery

NEXUS يستطيع معرفة:

- البرامج المثبتة.
- مساراتها.
- العمليات الحالية.
- النوافذ المفتوحة.
- أنواع التطبيقات.

حتى يستطيع اختيار طريقة تشغيلها.

---

# 141. Process Manager

مسؤول عن:

```text
Start
Stop
Inspect
Monitor
Recover
```

ولا يقتل process خارج المهمة بلا سبب.

---

# 142. Terminal System

يجب أن يدعم:

```text
CMD
PowerShell
Python
Git
Node
package managers
development CLIs
```

حسب الموجود في الجهاز.

---

# 143. Filesystem System

Capabilities:

```text
Read
Write
Edit
Create
Move
Copy
Delete
Rename
Search
Compress
Extract
```

مع Scope validation قبل التنفيذ.

---

# 144. File Transfer

الـRemote Web يستطيع طلب ملف من الكمبيوتر:

```text
Phone
↓
Request file
↓
NEXUS permission/scope
↓
Prepare transfer
↓
Download to phone
```

ولا يلزم نقل الملف إلى cloud service.

---

# 145. Remote Web

سيكون آخر جزء من المنتج.

الموقع:

> HTML5/JS static frontend مستضاف مثل GitHub Pages.

لكن:

> GitHub Pages لا تشغل الـAgent.

هي مجرد Remote Client.

```text
Phone Browser
↓
NEXUS Remote UI
↓
Secure Realtime Connection
↓
NEXUS Core on PC
```

---

# 146. Remote Features

من الهاتف:

- فتح Conversation.
- إرسال Prompt.
- مشاهدة Task.
- مشاهدة Activity.
- إرسال تعليمات جديدة.
- Pause.
- Resume.
- Stop.
- استلام Notifications.
- طلب ملفات.
- رؤية حالة الكمبيوتر.
- التحكم في المهام.

---

# 147. Realtime Channel

هناك فصل بين:

```text
Control/Data channel
Video/Screen channel
```

وذلك حتى لا يصبح بث الشاشة هو نفسه قناة الأوامر.

---

# 148. Remote Computer View

هدف NEXUS النهائي:

> إحساس أنك أمام الكمبيوتر وأنت على الهاتف.

هذا يتطلب لاحقًا:

```text
Realtime events
+
Screen/stream
+
Input channel
+
File transfer
+
Task channel
```

وليس مجرد screenshot كل فترة.

---

# 149. RustDesk كمرجع

RustDesk مشروع remote desktop مفتوح المصدر وself-hostable وله دعم Windows وميزات remote control، وهو مفيد كمرجع معماري لهذا الجزء، لكنه ليس NEXUS نفسه.

قرار NEXUS:

> **Reference، وربما reuse محدود جدًا حسب الترخيص وملاءمة المكونات.**

---

# 150. Remote Security

لا نسمح للهاتف أن يكون مستخدمًا داخل الشبكة فقط.

الجلسة يجب أن ترتبط بـ:

```text
Remote Session ID
Device identity
Authorization
Task Scope
```

والـRemote command يمر عبر NEXUS Core.

---

# 151. Notification System

Events مثل:

```text
task.completed
task.failed
task.recovered
task.blocked
resource.warning
```

تصل إلى:

- Windows notification.
- Remote Web.

---

# 152. UI Customization

المستخدم يريد:

- Dark.
- Light.
- وأشكال تخصيص إضافية معقولة.

لكن لا نبني "1500 إعداد".

نستخدم:

```text
Theme
Density
Font size
Layout
Language
Activity verbosity
```

---

# 153. Activity Verbosity

مثلاً:

### Compact

```text
→ Researching
→ Coding
→ Testing
```

### Detailed

```text
Agent
Tool
Result
Decision
Verification
```

---

# 154. Desktop Overlay Controls

يجب أن يظهر:

```text
NEXUS is working
[Pause]
[Resume]
```

عند Computer Use.

---

# 155. Emergency Control

لا نريد hotkey إجباريًا حسب قرارك الحالي.

لكن يجب أن تكون هناك وسيلة آمنة دائمًا:

```text
Overlay
Tray
Task control UI
```

لإيقاف Computer Control أو المهمة.

---

# 156. Security Model

Security ثلاثي الطبقات:

```text
Scope
+
Permission
+
Execution Gate
```

---

# 157. Scope Policy

هل العملية مرتبطة بالمهمة؟

---

# 158. Permission Policy

هل المهمة تسمح بهذا النوع من الفعل؟

---

# 159. Execution Gate

هل الوضع الحالي، والـworkspace، والـresource، والـapplication يسمحون بتنفيذها؟

---

# 160. Credential Architecture

NEXUS يحتاج Secret abstraction:

```text
Credential
├── ID
├── Provider
├── Scope
├── Reference
├── Created
└── last-used
```

والـAgent يحصل على reference.

---

# 161. Secret Redaction

يجب منع ظهور secrets في:

```text
Chat
Logs
Memory
Telemetry
Errors
Screenshots where possible
```

---

# 162. Memory Security

Memory poisoning خطر حقيقي في أنظمة تتعلم.

لذلك:

```text
Raw experience
↓
Candidate lesson
↓
Evidence
↓
Confidence
↓
Persist
```

ولا تصبح المعلومة قاعدة دائمة بمجرد أن قالها Agent.

---

# 163. Tool Risk Classification

كل Tool تحمل:

```text
risk:
low
medium
high
```

مثلاً:

```text
Read file = low

Edit file = medium

Delete file = high

Run unrestricted command = high

Push release = high
```

لكن L4 يستطيع تنفيذها إذا كانت ضمن المهمة وسياسة المهمة.

---

# 164. Audit Log

وجود Audit Log لا يعني أن المنصة تصبح ثقيلة.

هو سجل:

```text
Who
What
When
Where
Result
```

مثال:

```text
10:31
Agent: Coder
Action: edit
File: M:\Project\auth.py

10:33
Agent: Tester
Action: run
Command: pytest
Result: 2 failures
```

---

# 165. Audit vs Activity

### Activity

ما يراه المستخدم.

### Audit

سجل تقني أدق للاستعادة والتحقق والتشخيص.

---

# 166. Repository Licenses

لا يكفي أن يكون المشروع MIT.

نحتاج:

```text
License inventory
Version pin
Notice tracking
Attribution
Dependency policy
Model license review
```

لأن بعض المستودعات تجمع مكونات بتراخيص مختلفة.

مثال OpenHands يوضح أن الـcore والـagent-server MIT بينما enterprise directory له ترخيص مختلف.

---

# 167. Repository Integration Policy

كل Repo يدخل في واحدة:

### USE
مكوّن مباشر.

### ADAPT
مكوّن يتم تغليفه أو تعديله.

### REFERENCE
نتعلم منه architecture/idea.

### TEST
للتقييم فقط.

### REJECT
لا يدخل.

---

# 168. Repository Ownership Boundary

لا Repository خارجي يمتلك:

- NEXUS Task State.
- NEXUS Scope.
- NEXUS Permission system.
- NEXUS Memory semantics.
- NEXUS identity.
- NEXUS resource policy.

هذه ملك NEXUS.

---

# 169. Integration Map

| الطبقة | المرشح | القرار |
|---|---|---|
| Harness | ECC | ADAPT/REFERENCE |
| Agent SDK | Cline | ADAPT/REFERENCE |
| Orchestration | LangGraph | USE/ADAPT |
| Long-horizon | Prime | REFERENCE |
| Multi-agent | MAF | REFERENCE/POSSIBLE USE |
| Coding | OpenHands | ADAPT/REFERENCE |
| Coding | OpenCode | REFERENCE/POSSIBLE COMPONENT |
| Codebase | Aider | ADAPT IDEAS |
| Browser Agent | Browser Use | USE/ADAPT |
| Browser Harness | Browser Harness | ADAPT |
| Browser Execution | Playwright | USE |
| Windows | windows-harness | ADAPT |
| Windows UI | pywinauto | USE |
| Vision Research | UI-TARS/OpenCUA | REFERENCE |
| Memory | Mem0 | USE/ADAPT |
| Vector Search | Qdrant | USE |
| Parsing | Tree-sitter | USE |
| Documents | Docling | USE |
| Speech | sherpa-onnx | BENCHMARK/USE |
| Local LLM | llama.cpp | USE |
| Protocol | MCP | USE SELECTIVELY |
| Desktop evaluation | OSWorld | TEST |
| Browser evaluation | BrowserGym | TEST |
| Security | Trivy/Semgrep/Pyright | USE SELECTIVELY |
| Remote | RustDesk/WebRTC research | REFERENCE |

---

# 170. لماذا Cline مهم؟

لأن الـSDK الحالي يثبت separation جيد جدًا:

```text
Shared
↓
LLM
↓
Agents
↓
Core
↓
Apps
```

مع stateful Core وsession lifecycle وplugins وtools وevents.

وهذا pattern مرشح جدًا لطبقة NEXUS Agent Runtime.

---

# 171. لماذا Prime مهم؟

لأن NEXUS يريد بالضبط:

```text
Long-running
Persistent
Subagents
Memory
Skills
Background
Resume
Learning
```

وهذه كلها موجودة كمفاهيم أساسية فيه.

لكننا لا ننسخ التصميم بالكامل.

---

# 172. لماذا Browser Use مهم؟

لأن المطلوب ليس فقط:

> "افتح URL."

بل:

> "نفّذ مهمة كاملة في الويب."

ومشروع Browser Use يركز تحديدًا على إعطاء الـAI مساحة أفعال داخل browser الحقيقي، مع persistent tools وrecovery-related capabilities.

---

# 173. لماذا Windows Harness مهم؟

لأنه أقرب Repo وجدناه إلى:

```text
Windows
+
UIA
+
Input
+
Screen
+
Browser
+
Shell
+
Filesystem
```

وهو بالضبط ما نحتاجه كـexecution backend، مع ضرورة الحفاظ على abstraction بسبب كونه experimental.

---

# 174. لماذا OSWorld مهم؟

OSWorld-V2 في 2026 مخصص أصلًا لقياس Computer Use Agents في long-horizon real-world tasks، مع إصدارات reproducible pinned releases؛ الإصدار النشط الذي وجدناه هو 2026.08.08.

قرار NEXUS:

> نستخدمه كاختبار خارجي، وليس داخل runtime.

---

# 175. BrowserGym

BrowserGym يوفر بيئة واختبارات للـweb agents، ويضم WebArena وVisualWebArena وWorkArena وغيرها، لكنه يوضح بنفسه أنه framework بحثي وليس consumer product.

قرار NEXUS:

> TESTING ONLY.

---

# 176. Model Routing مقابل Multiple Models

NEXUS قد يملك:

```text
Model A
Model B
Model C
```

لكن لا يعني أنها كلها تعمل معًا.

Resource Manager يقرر:

```text
Load
Keep warm
Unload
```

حسب الجهاز.

---

# 177. Multi-Agent لا يعني Multi-LLM

هذه قاعدة مهمة.

يمكن:

```text
1 Model
↓
5 Agent roles
```

أو:

```text
2 Models
↓
10 Agents
```

ولا يشترط أن كل Agent يملك نموذجًا مستقلًا.

هذا مهم جدًا لجهازك.

---

# 178. Model Selection

Model Router يضع score:

```text
Task fit
+
Capabilities
+
RAM
+
VRAM
+
Latency
+
Context
+
Observed reliability
```

ثم يختار.

---

# 179. Resource-aware Concurrency

مثلاً:

```text
RAM low
→ 1-2 agents

RAM available
→ parallelize more

VRAM occupied
→ CPU model candidate

GPU free
→ GPU-specialized model
```

ولا يوجد رقم ثابت عالمي.

---

# 180. Hardware Benchmark Database

NEXUS يحتفظ:

```text
Model
Hardware
Context
Quantization
Throughput
Memory
Latency
Stability
```

فتصبح توصيات Router مبنية على benchmark حقيقي.

---

# 181. Model Fallback

لو النموذج الأساسي غير قادر:

```text
Primary Model
↓
Failure
↓
Alternative local model
↓
Specialist
↓
Search
↓
External consultation
```

---

# 182. Task Decomposition

NEXUS يقسم:

```text
Goal
↓
Milestones
↓
Subtasks
↓
Agents
↓
Tools
```

لكن المستخدم لا يجبره على كتابة الخطة يدويًا.

---

# 183. Dynamic Replanning

إذا ظهر شيء جديد:

```text
New fact
↓
Current plan invalid/incomplete
↓
Recalculate affected steps
↓
Preserve completed work
↓
Continue
```

ولا يعيد المشروع من الصفر.

---

# 184. "الخطة لا تفشل"

المعنى الهندسي:

> قد تفشل **محاولة**، لكن ليس الهدف.

مثال:

```text
Approach A fails
↓
Approach B
↓
Approach C
↓
Research
↓
Repair
```

---

# 185. Task Deadlines

يدعم:

```text
Duration based
Goal based
Hybrid
```

مثال:

> "أنجزه خلال نصف ساعة."

أو:

> "استمر حتى تنتهي."

---

# 186. Waiting States

إذا NEXUS يحتاج شيئًا لا يمكن جمعه ذاتيًا:

```text
WAITING_FOR_USER
```

لكن لا نستخدم الحالة إلا إذا:

> القرار لا يمكن استنتاجه أو جمعه من المصادر المتاحة.

---

# 187. Offline Waiting

إذا الشبكة فقط هي الناقصة:

```text
WAITING_NETWORK
```

وليس:

```text
WAITING_USER
```

---

# 188. Power-loss Recovery

المطلوب:

```text
Save
↓
Power loss
↓
Boot
↓
Detect interrupted task
↓
Inspect
↓
Resume
```

وهو متوافق مع متطلباتك المكتوبة حول إعادة التشغيل والاستمرار بعد الانقطاع.

---

# 189. Checkpoint History UI

شاشة صغيرة:

```text
Task: Client SaaS

Today
18:20 — Architecture
18:47 — Backend
19:15 — Tests
19:34 — Fix auth
19:52 — Verification
```

يمكنك:

> فتح checkpoint.

ومراجعة حالتها.

---

# 190. Scoped Restore

مثال:

> "رجع المشروع قبل تعديل auth."

يتم:

```text
Git/File rollback
```

بدون مسح:

```text
Learning
Memory
Conversation
```

---

# 191. NEXUS API

الـCore يعرّف APIs:

```text
/tasks
/sessions
/agents
/tools
/memory
/models
/workspaces
/computer
/git
/github
/events
/system
/remote
```

---

# 192. Task API

```text
createTask
startTask
pauseTask
resumeTask
cancelTask
getTask
getEvents
getCheckpoints
```

---

# 193. Agent API

```text
registerAgent
runAgent
pauseAgent
stopAgent
getAgentState
getCapabilities
```

---

# 194. Tool API

```text
discoverTool
checkTool
executeTool
verifyTool
```

---

# 195. Memory API

```text
remember
retrieve
search
update
forget
summarize
```

---

# 196. Model API

```text
list
benchmark
load
unload
select
health
```

---

# 197. Computer API

```text
listWindows
focusWindow
captureScreen
uiaQuery
click
type
scroll
mouseMove
keyboard
clipboard
```

مع سياسات scope/permission.

---

# 198. Git API

```text
status
branch
diff
commit
merge
push
pull
rollback
```

---

# 199. GitHub API

```text
search
repo
clone
issues
pullRequests
releases
push
```

---

# 200. Event Schema

كل event:

```text
id
type
timestamp
task_id
session_id
agent_id
source
payload
severity
```

---

# 201. Error Model

كل خطأ:

```text
error_id
type
source
task
agent
tool
message
context
recovery_possible
recovery_action
resolved
```

---

# 202. Error Taxonomy

```text
MODEL_ERROR
TOOL_ERROR
NETWORK_ERROR
WINDOW_ERROR
FILESYSTEM_ERROR
APPLICATION_ERROR
RESOURCE_ERROR
AUTH_ERROR
VALIDATION_ERROR
STATE_ERROR
DEPENDENCY_ERROR
UNKNOWN_ERROR
```

---

# 203. Error Recovery Matrix

```text
MODEL_ERROR
→ retry / alternate model

TOOL_ERROR
→ retry / alternative tool

NETWORK_ERROR
→ offline continuation / wait

WINDOW_ERROR
→ refocus / reopen

FILESYSTEM_ERROR
→ inspect scope/permissions

RESOURCE_ERROR
→ reduce load

AUTH_ERROR
→ credential path

VALIDATION_ERROR
→ repair
```

---

# 204. Health Monitor

المراقبة تشمل:

```text
Core
Workers
Model runtime
Browser runtime
Computer runtime
Database
Storage
Network
Remote gateway
```

---

# 205. Doctor Mode

نظام تشخيص:

```text
NEXUS Doctor
├── Core
├── Model
├── GPU
├── RAM
├── Browser
├── Windows automation
├── Database
├── Tools
├── Remote
└── Plugins
```

يحدد المشاكل ويقترح إصلاحها.

---

# 206. Self-Diagnostics

قبل مهمة كبيرة:

```text
Can required tool run?
Is model available?
Enough disk?
Enough RAM?
Browser available?
Git installed?
```

إذا في نقص:

> يعالجه إن كان ضمن الصلاحيات، أو ينبه المستخدم قبل بدء المهمة.

---

# 207. Application Installation

إذا مهمة تحتاج dependency:

> NEXUS يستطيع تثبيتها إذا كانت ضمن صلاحيات المهمة.

مثلاً:

```text
npm package
Python package
CLI tool
```

لكن عمليات تثبيت النظام الأوسع تخضع لسياسة النظام وWorkspace/Task.

---

# 208. Package Management

حسب المشروع:

```text
pip
npm
pnpm
npm
cargo
dotnet
gradle
```

وأي package manager متوفر.

---

# 209. Browser Authentication

NEXUS يدعم التعامل مع مواقع تتطلب تسجيل دخول **عندما تكون المهمة تتطلب ذلك**.

لكن:

- لا يعرض كلمات المرور في logs.
- لا ينسخ secrets إلى memory.
- لا يرسلها لخدمة خارجية بلا سبب.
- لا يحاول تجاوز الحماية.

---

# 210. External AI Account Use

إذا المستخدم يريد:

> "روح اسأل الخدمة الفلانية."

يمكن NEXUS استعمال الموقع أو API المناسب ضمن المهمة.

لكن:

> لا يجعل بيانات المستخدم المحلية مكشوفة أكثر من المطلوب.

---

# 211. Security Boundary for External AI

قبل الإرسال:

```text
Payload
↓
Classify data
↓
Need-to-send?
↓
Redact if possible
↓
Send
```

---

# 212. Internet Research Cache

المصادر المهمة قد تحفظ داخل Task:

```text
URL
Title
Date
Evidence
Summary
Confidence
```

حتى لا يحتاج NEXUS إعادة اكتشافها كل مرة.

---

# 213. Knowledge Base

المعلومات المستقرة من المشاريع:

```text
Architecture
APIs
Libraries
Decisions
Docs
```

يمكن تخزينها في Workspace Knowledge.

---

# 214. Knowledge Freshness

كل معلومة خارجية تحمل:

```text
source date
retrieved date
confidence
```

حتى لا تعامل معلومة قديمة كحقيقة أبدية.

---

# 215. Agent Learning from Errors

مثال:

```text
Error:
Tool X fails when path contains spaces.

Lesson:
Use quoted path arguments.
```

ثم لاحقًا:

> يتجنب الخطأ.

---

# 216. Learning Scope

درس محلي لمشروع:

> لا ينتشر إلى كل NEXUS.

درس عام:

> ينتقل فقط إذا ثبت أنه generalizable.

---

# 217. Project-specific Rules

كل Project يستطيع أن يملك:

```text
coding conventions
naming
architecture rules
test rules
deployment rules
```

وتسبقها تعليمات المهمة الحالية.

---

# 218. User Preferences

مثل:

> "استخدم أسلوب تسمية معين."

تحفظ عالميًا أو في Workspace.

---

# 219. Prompt Override

إذا قلت اليوم:

> "في هذا المشروع استخدم PostgreSQL رغم تفضيلي السابق."

هذه المهمة تتبع PostgreSQL.

---

# 220. Observability

نحتاج:

```text
Task metrics
Agent metrics
Model metrics
Tool metrics
Resource metrics
Recovery metrics
```

لكن لا نعرض كل ذلك للمستخدم افتراضيًا.

---

# 221. Metrics

أهم المقاييس:

```text
Task completion rate
Verification pass rate
Repair count
Average recovery time
Tool failure rate
Model latency
Memory use
CPU use
GPU use
```

---

# 222. Evaluation Framework

NEXUS يحتاج اختبارات داخلية وخارجية.

## Internal

- Unit
- Contract
- Integration
- E2E
- Recovery
- Resource
- Security

## External

- OSWorld
- BrowserGym
- SWE-style tasks

OSWorld-V2 حاليًا يركز على long-horizon computer use، وBrowserGym على web-agent evaluation.

---

# 223. Fault Injection

نختبر:

```textInternet loss
Power loss
Process crash
Model crash
Browser crash
Corrupt file
Tool failure
RAM pressure
Disk low
Git conflict
Bad external answer
```

---

# 224. Acceptance Test — Long Task

نعطي NEXUS:

> "ابنِ مشروعًا كاملًا."

ويجب:

```textPlan
Research
Build
Test
Repair
Checkpoint
Continue
Verify
```

دون تدخل مستمر.

---

# 225. Acceptance Test — Word

يجب:

```textOpen Word
Create content
Search sources
Insert images
Format
Save
Verify
```

---

# 226. Acceptance Test — Browser

يجب:

```textOpen browser
Search
Compare
Navigate
Login where authorized
Download
Upload
Verify
```

---

# 227. Acceptance Test — Large Repository

```textClone
Index
Understand
Map
Modify
Test
Review
```

دون تحميل repository كاملًا في context.

---

# 228. Acceptance Test — Recovery

```textStart task
↓
Checkpoint
↓
Kill process
↓
Restart NEXUS
↓
Detect
↓
Recover
↓
Inspect reality
↓
Continue
```

---

# 229. Acceptance Test — Offline

```textTask
↓
Disconnect internet
↓
Continue local work
↓
Reach network dependency
↓
WAITING_NETWORK
↓
Restore internet
↓
Continue
```

---

# 230. Acceptance Test — Human + AI

```textUser → Game
NEXUS → Browser

User → own window
NEXUS → own window
```

ويجب ألا يسبب التحكم المتبادل فسادًا في الإدخال.

---

# 231. Acceptance Test — Learning

```textPerform repeated workflow
↓
Detect pattern
↓
Create candidate Skill
↓
Test
↓
Persist
↓
Reuse
```

---

# 232. Acceptance Test — Model Routing

```textMultiple models installed
↓
Task
↓
Benchmark profiles
↓
Resource status
↓
Select
↓
Execute
```

---

# 233. Acceptance Test — Voice

```textArabic speech
↓
Transcription
↓
Intent
↓
Task
```

ثم:

```textMixed Arabic-English
```

ويجب أن يحافظ النظام على المصطلحات التقنية.

---

# 234. Packaging

يجب أن تكون عملية التثبيت:

```textInstall NEXUS
↓
Hardware scan
↓
Dependency check
↓
Model setup
↓
Tool discovery
↓
Workspace defaults
↓
Ready
```

---

# 235. First-run Setup

يعرض:

```textHardware
Storage
Models
Browser
Git
GitHub optional
Speech
Computer Use
```

ويترك للمستخدم اختيار ما يريد.

---

# 236. Model Download

يمكن NEXUS تنزيل نماذج مناسبة عند الإعداد الأولي، لكن:

- يعرض الحجم.
- يوضح مكان التخزين.
- يتحقق من الملف.
- يسجل version/hash.
- لا ينزل نموذجًا غير متوافق مع الجهاز دون سبب.

متطلبك الأصلي ينص صراحةً على إمكانية تنزيل النماذج أثناء إعداد المنصة وتشغيل نماذج محلية مثبتة مسبقًا.

---

# 237. Model Compatibility

كل Model يحمل:

```text
CPU compatibility
GPU compatibility
VRAM
RAM
Context
Quantization
Language
Task type
```

---

# 238. NEXUS Computer Capability Matrix

| القدرة | المستوى المطلوب |
|---|---|
| Files | Native |
| Terminal | Native |
| Windows | Native/UIA |
| Mouse | Computer |
| Keyboard | Computer |
| Screenshot | Computer |
| Browser | Browser runtime |
| Word | Windows Computer |
| PowerPoint | Windows Computer |
| Blender | Windows Computer |
| AutoCAD | Windows Computer |
| Git | Native |
| GitHub | API/Web |
| Web | Browser/Web |
| External AI | Web/API |
| Vision | Model/tool |
| Speech | Local speech |
| Documents | Docling + app runtime |

---

# 239. Plugin Development SDK

في المستقبل:

```text
NEXUS SDK
├── Tool SDK
├── Agent SDK
├── Skill SDK
├── Model SDK
├── Plugin SDK
├── Event SDK
└── Remote SDK
```

---

# 240. Developer API

مطور خارجي يستطيع:

```text
registerAgent()
registerTool()
registerSkill()
registerModel()
subscribeEvent()
requestMemory()
requestTask()
```

---

# 241. Plugin Isolation

ليس كل Plugin يحصل على كل صلاحيات NEXUS.

يحصل على:

```textDeclared permissions
```

---

# 242. Self-Building Capabilities

NEXUS يستطيع مستقبلًا:

```textNeed capability
↓
Search registry
↓
No matching tool
↓
Generate tool
↓
Test
↓
Register temporary
↓
Evaluate
↓
Promote to permanent Skill/Tool
```

---

# 243. Self-Modifying Core

NEXUS لا يعدل Core نفسه بشكل حر.

القاعدة:

```textCore change proposal
↓
Review
↓
Tests
↓
Checkpoint
↓
Apply
```

ولا يتم اعتماد تغييرات خطيرة دون آلية آمنة.

---

# 244. NEXUS as Platform

النتيجة النهائية ليست:

> App.

بل:

> **Platform**

يمكن أن يعيش فوقه:

```textTools
Agents
Skills
Models
Plugins
Projects
Workspaces
```

---

# 245. Data Directory Concept

التنظيم المفاهيمي:

```text
NEXUS/
├── config/
├── data/
├── models/
├── memory/
├── workspaces/
├── tasks/
├── checkpoints/
├── logs/
├── plugins/
└── cache/
```

المسارات الفعلية قابلة للتخصيص.

---

# 246. Workspace Directory

```text
Workspace/
├── project/
├── .nexus/
│   ├── state
│   ├── index
│   ├── memory refs
│   ├── task metadata
│   └── decisions
```

---

# 247. Task State

كل Task يملك حالة قابلة للحفظ.

مفهوميًا:

```json
{
  "task_id": "…",
  "goal": "…",
  "workspace": "…",
  "status": "executing",
  "phase": "testing",
  "active_agents": [],
  "checkpoint": "…",
  "dependencies": [],
  "policy": {},
  "recovery": {}
}
```

---

# 248. Agent Contract

المخرَج لا يكون نصًا حرًا فقط.

مفهوميًا:

```json
{
  "status": "ready_for_verification",
  "summary": "Authentication module implemented",
  "changed_files": [],
  "evidence": [],
  "next_action": "run_tests"
}
```

---

# 249. Tool Contract

كل Tool:

```json
{
  "tool": "filesystem.read",
  "input": {},
  "scope": "...",
  "permissions": [],
  "result": {},
  "verification": {}
}
```

---

# 250. Verification Contract

```json
{
  "criterion": "project_builds",
  "method": "npm_build",
  "result": "passed",
  "evidence": {}
}
```

---

# 251. Checkpoint Contract

```json
{
  "checkpoint_id": "…",
  "task_id": "…",
  "phase": "backend_complete",
  "workspace_state": {},
  "git_state": {},
  "agent_state": {},
  "timestamp": "…"
}
```

---

# 252. Memory Contract

```json
{
  "type": "lesson",
  "scope": "workspace",
  "content": "…",
  "source": "task",
  "confidence": 0.92
}
```

---

# 253. Model Contract

```json
{
  "model_id": "…",
  "backend": "llama.cpp",
  "capabilities": ["coding"],
  "ram_mb": 1200,
  "vram_mb": 1000,
  "context": 8192,
  "benchmark": {}
}
```

---

# 254. Remote Contract

```json
{
  "session_id": "…",
  "device": "phone",
  "task": "…",
  "action": "pause",
  "authorization": "…"
}
```

---

# 255. NEXUS Repository Structure

المشروع نفسه يمكن أن يكون:

```text
nexus/
├── core/
├── orchestration/
├── agents/
├── tools/
├── computer/
├── browser/
├── models/
├── memory/
├── learning/
├── verification/
├── recovery/
├── git/
├── github/
├── plugins/
├── skills/
├── events/
├── resources/
├── remote/
├── ui/
├── tests/
└── docs/
```

---

# 256. Core Package

```text
core/
├── tasks
├── sessions
├── policies
├── lifecycle
├── events
└── errors
```

---

# 257. Orchestration Package

```text
orchestration/
├── planners
├── scheduler
├── state
├── graph
├── delegation
└── replanning
```

---

# 258. Agent Package

```text
agents/
├── master
├── planner
├── research
├── coding
├── computer
├── browser
├── test
├── security
└── registry
```

---

# 259. Computer Package

```text
computer/
├── screen
├── windows
├── mouse
├── keyboard
├── uia
├── vision
├── processes
├── clipboard
└── arbitration
```

---

# 260. Browser Package

```text
browser/
├── sessions
├── playwright
├── browser_use
├── navigation
├── downloads
├── uploads
└── verification
```

---

# 261. Memory Package

```text
memory/
├── manager
├── schemas
├── retrieval
├── compaction
├── ranking
├── qdrant
├── mem0
└── sqlite
```

---

# 262. Recovery Package

```text
recovery/
├── checkpoints
├── reconciliation
├── restart
├── rollback
├── health
└── recovery policies
```

---

# 263. Security Package

```text
security/
├── scope
├── permissions
├── credentials
├── secrets
├── audit
├── policy
└── redaction
```

---

# 264. UI Package

```text
ui/
├── chat
├── tasks
├── activity
├── models
├── workspace
├── settings
├── overlay
└── tray
```

---

# 265. Remote Package

```text
remote/
├── gateway
├── authentication
├── events
├── control
├── file_transfer
└── realtime
```

---

# 266. Dependency Principle

NEXUS Core لا يعتمد مباشرة على:

```textBrowser Use classes
Cline classes
ECC files
Mem0 internals
Qdrant internals
```

بل:

```textNEXUS Interface
↓
Adapter
↓
External project
```

---

# 267. لماذا هذا مهم؟

إذا توقف Repository خارجي:

```textExternal project unavailable
↓
Replace adapter
↓
NEXUS continues
```

---

# 268. Version Pinning

لكل external dependency:

```textRepo
Commit/Tag
Version
License
Hash/package version
Compatibility
```

حتى لا يتغير سلوك NEXUS فجأة.

---

# 269. License Audit

قبل الدمج:

```textLicense
Subdependencies
Model license
Assets license
Generated code
Attribution
```

---

# 270. Repository Security Audit

قبل إدخال Repo:

```textMaintenance
Issues
Security policy
Dependency vulnerabilities
Install scripts
Network behavior
Credentials
```

---

# 271. نشاط المشاريع

النشاط لا يُقاس بالنجوم فقط.

نراقب:

```textRecent commits
Release cadence
Open issues
Security activity
PR activity
Maintainers
Breaking changes
```

مثال:

Cline حاليًا لديه نشاط واسع وإصدارات مستمرة.

Browser Use لديه 129 releases حاليًا حسب GitHub.

Tree-sitter لديه releases مستمرة أيضًا، والإصدار 0.26.9 كان الأحدث في نتيجة البحث المستخدمة.

---

# 272. أمثلة على مشاريع لا ندخلها دون سبب

### AutoGen
لا يكون الاختيار الجديد الأساسي عندما تكون Microsoft نفسها تدفع المستخدمين نحو Agent Framework.

### LLM Guard
لا نعتمد عليه كمكون جديد إذا كان المستودع archived.

### DirectML
لا نعتمد عليه كمسار استراتيجي جديد.

### vLLM/SGLang
ليس اختيار NEXUS الحالي على جهاز Windows/Hardware الحالي.

### TGI
ليس ضمن المسار بسبب وضعه الحالي.

الهدف ليس الحكم على جودة هذه المشاريع، بل ملاءمتها لهذا المنتج الآن.

---

# 273. Microsoft Agent Framework

MAF حاليًا framework مفتوح لبناء agents وmulti-agent workflows في Python و.NET، ويقدم local development وكذلك تكاملات مع منظومة Microsoft. وتذكر صفحته الرسمية أنه يثبت على Windows وأن Python و.NET كلاهما مدعومان.

قرار NEXUS:

> **Reference / possible orchestration layer.**

---

# 274. Why not one framework?

لأن:

```textECC
= Harness ideas

Cline
= Agent runtime ideas

LangGraph
= Stateful orchestration

Prime
= Long-horizon / continual

Browser Use
= Browser intelligence

Windows Harness
= Windows execution
```

كل مشروع يحل جزءًا مختلفًا.

---

# 275. NEXUS Super-Harness

الفكرة النهائية:

```text
External ecosystems
       │
       ▼
NEXUS adapters/interfaces
       │
       ▼
NEXUS Core
```

وليس:

```text
Repo A
+ Repo B
+ Repo C
```

---

# 276. Final End-to-End Example

المستخدم:

> "ابنِ لي منصة SaaS على القرص M، ابحث أولًا عن أفضل architecture، حلل مشاريع GitHub المشابهة، أنشئ المشروع، اختبره، أصلح كل الأخطاء، وارفعه على GitHub."

NEXUS:

```text
1. Understand
2. Clarification Gate
3. Scope
4. Workspace
5. Research
6. GitHub discovery
7. Architecture
8. Task decomposition
9. Agent scheduling
10. Model selection
11. Repository setup
12. Coding
13. Tests
14. Debugging
15. Security
16. Review
17. Git
18. GitHub
19. Final verification
20. Memory
21. Learning
22. Report
```

---

# 277. Example — "كمل المشروع"

المستخدم لاحقًا:

> "كمل المشروع."

NEXUS:

```text
Conversation lookup
↓
Task lookup
↓
Workspace lookup
↓
Checkpoint
↓
Current filesystem
↓
Git state
↓
Memory
↓
Next valid action
```

ثم يكمل.

---

# 278. Example — Computer Task

> "افتح Word واعمل التقرير."

```text
Master
↓
Document Agent
↓
Research
↓
Windows Agent
↓
Word
↓
Computer Runtime
↓
Verification
```

---

# 279. Example — Browser + Game Parallel

```text
User
↓
War Thunder
```

وفي الوقت نفسه:

```text
NEXUS
↓
Chrome session
↓
Research / Project task
```

Window Manager يفصل المسؤوليات.

---

# 280. Example — External AI Consultation

```text
Local model
↓
Unsure
↓
Web
↓
External AI
↓
Evidence
↓
Verification
↓
Continue
```

---

# 281. Example — Network Loss

```text
Research
↓
Internet unavailable

Coding
↓
continues locally

Testing
↓
continues locally

Research
↓
WAITING_NETWORK
```

وعند العودة:

```text
Research
↓
Resume
```

---

# 282. Example — Power Loss

```text
Task
↓
Checkpoint
↓
Power loss
↓
Windows boot
↓
NEXUS tray starts
↓
Recovery manager
↓
Inspect
↓
Resume
```

---

# 283. Example — Model Failure

```text
Model A
↓
Failed

Model B
↓
Try

Specialist
↓
Try

Research
↓
Try

External AI
↓
Verify

Continue
```

---

# 284. Example — New Skill

بعد عدة مهام:

```text
Pattern detected
↓
Create Skill candidate
↓
Test
↓
Register
```

---

# 285. Example — New Tool

```text
Agent needs tool
↓
Registry search
↓
Not found
↓
Build tool
↓
Test
↓
Use
↓
Keep if useful
```

---

# 286. Remote Web Final Experience

الهاتف يفتح:

```text
NEXUS Remote
```

ويرى:

```text
Conversation A
✓ Complete

Conversation B
→ Working

Conversation C
⏸ Paused
```

يدخل B:

```text
Planner
✓

Research
✓

Coder
→

Tester
Pending
```

ثم يرسل:

> "كمل."

ويصل الأمر إلى الـPC.

---

# 287. Remote File Retrieval

الهاتف:

> "جيبلي report.pdf"

NEXUS:

```text
Locate file
↓
Verify scope
↓
Package
↓
Transfer
↓
Phone download
```

---

# 288. UI Design Principle

واجهة NEXUS:

> Familiar > Artistic.

نأخذ أفضل أنماط:

- Codex.
- Claude.
- Cursor.
- Perplexity.

لكن نستخدم هوية NEXUS.

---

# 289. No Artificial Complexity

لا نريد:

```text
200 dashboard metrics
```

بل:

```text
Task
Activity
Tools
Files
Result
```

والتفاصيل تظهر عند الطلب.

---

# 290. Installation Modes

### Minimal

Core + one model + essential tools.

### Full

Core + models + browser + computer + document + Git.

### Developer

كل الأدوات + SDK + plugins + debug.

---

# 291. Hardware-specific startup

NEXUS عند التشغيل يقرر:

```text
What models can be active?
What services must run?
What can stay off?
```

ولا يستهلك الموارد لمجرد أن القدرة موجودة.

---

# 292. Background Resource Policy

عندما لا توجد مهام:

```text
Core active
Memory active
Scheduler active
Most heavy inference inactive
```

حتى لا يثقل الجهاز.

---

# 293. Active Task Resource Policy

عند المهمة:

```text
Load required model
Start required workers
Enable required tools
Reduce irrelevant services
```

---

# 294. Model Warmth

يمكن:

```text
Keep model warm
```

إذا كان المستخدم سيحتاجه كثيرًا.

أو:

```text
Unload
```

إذا كانت الموارد محدودة.

---

# 295. Hardware Change

إذا أضيف:

```textRAM
GPU
Storage
```

NEXUS:

```textDetect
↓
Benchmark/reprofile
↓
Update model catalog
↓
Update resource policy
```

---

# 296. NEXUS Doctor

إذا الجهاز تغير أو حدث خطأ:

```text
NEXUS Doctor
↓
Hardware
↓
Drivers/runtime
↓
Models
↓
Tools
↓
Browser
↓
Database
```

ويعطي أسبابًا قابلة للفهم.

---

# 297. Versioning

NEXUS يجب أن يعرف:

```textCore version
Tool version
Agent version
Model version
Plugin version
Workspace schema
```

---

# 298. Migration

عند تحديث NEXUS:

```textBackup state
↓
Migrate DB
↓
Migrate workspace
↓
Check compatibility
↓
Start
```

ولا يخسر الذاكرة.

---

# 299. Backup

النسخ الاحتياطية تشمل:

```textTask state
Memory metadata
Workspace metadata
Settings
Checkpoints
```

وملفات المشاريع حسب policy.

متطلباتك الأصلية تنص على نسخ احتياطية متكررة تشمل الحالة والخطط والذاكرة والملفات والمشاريع والإعدادات والسجل، وإتاحة الاستعادة إلى نسخة سابقة.

---

# 300. Backup Rotation

يجب وجود:

```textDaily
Milestone
Pre-risk
Post-major change
```

وإدارة مساحة التخزين.

---

# 301. Project Backup vs Memory Backup

لا يجب أن يكونا نفس الشيء.

```textProject rollback
≠
Memory rollback
```

حتى نحافظ على الخبرة.

---

# 302. Core State and Artifact Separation

```textState
+
Artifacts
```

منفصلان.

---

# 303. Project Artifact

مثلاً:

```textapp source code
reports
presentations
build artifacts
```

---

# 304. Memory Artifact

```textlessons
decisions
preferences
knowledge
```

---

# 305. Recovery Strategy

أفضل Resume:

```textCheckpoint
+
Actual state
+
Git
+
Memory
+
Process
```

ثم إعادة بناء Current World Model.

---

# 306. Current World Model

يصف:

```textWhat exists now?
What process runs?
What window is open?
What files exist?
What git commit is active?
What task phase is current?
```

---

# 307. World Model Update

بعد كل action:

```textAction
↓
Observation
↓
Update world model
```

وهذا مهم جدًا للـComputer Agent.

---

# 308. Computer State

```textDesktop
Windows
Apps
Processes
Focus
Files
```

---

# 309. Browser State

```textTabs
URL
Page
DOM
Session
Downloads
Uploads
```

---

# 310. Project State

```textFiles
Git
Build
Tests
Dependencies
Architecture
```

---

# 311. Task World State

```textGoal
Plan
Phase
Agents
Resources
Blockers
Verification
```

---

# 312. NEXUS Context Composer

المكون الذي يجمع:

```textTask State
+
World State
+
Relevant Memory
+
Tools
+
Agent role
```

ويقدم أصغر Context مفيد للنموذج.

---

# 313. Why this matters for 1B

بدل:

> "خذ كل شيء وافهم."

نقول:

> "هذه المهمة، وهذه الحالة، وهذه الأداة، وهذه الملفات ذات العلاقة."

وبالتالي تقل الحاجة إلى نموذج ضخم.

---

# 314. Code Context

في مشروع كبير:

```textCurrent issue
↓
Relevant modules
↓
Symbols
↓
Dependencies
↓
Tests
```

بدل كل المشروع.

---

# 315. Browser Context

بدل الصفحة كاملة:

```textRelevant DOM
+
Accessibility
+
Current screenshot
```

---

# 316. Memory Context

بدل كامل الذاكرة:

```textRelevant memories only
```

---

# 317. Research Context

بدل عشرات المواقع:

```textVerified claims
+
source evidence
```

---

# 318. Agent Context

كل Agent يحصل على:

```textRole
Task
Scope
Relevant context
Relevant tools
Expected output
```

---

# 319. Tool Result Compression

Tool قد يرجع آلاف الأسطر.

NEXUS:

```textRaw output
↓
Parser
↓
Important result
↓
Summary
↓
Artifact reference
```

لكن يحتفظ بالنص الخام محليًا عند الحاجة.

---

# 320. Artifact references

بدل إدخال ملف كامل للـModel:

```textFile stored
↓
Reference
↓
Read relevant portion
```

---

# 321. Document Retrieval

نفس المبدأ.

---

# 322. Model Prompt Design

Prompt النهائي لا يساوي:

```textSystem + user
```

بل:

```textSystem policy
+
Agent role
+
Task
+
Scope
+
Relevant memory
+
Tools
+
State
+
Verification requirements
```

---

# 323. Tool Calling

NEXUS يجب أن يفضّل structured tool calls عندما تكون ممكنة.

النص الحر يكون fallback.

---

# 324. Agent Output Validation

كل Agent output يمر:

```textSchema validation
↓
Semantic validation
↓
Task compatibility
```

---

# 325. Planner Validation

قبل تنفيذ الخطة:

```textDependencies
Scope
Tools
Resources
Success criteria
```

---

# 326. Plan Quality

الخطة الجيدة:

- قابلة للتنفيذ.
- قابلة للتحقق.
- لا تحتوي loop غير ضروري.
- لا تتطلب معلومات غير متاحة دون خطة للحصول عليها.
- تحافظ على artifacts الصحيحة.

---

# 327. Dynamic Planning

الخطة ليست عقدًا جامدًا.

لكن completed milestones لا تعاد.

---

# 328. Task Goal

كل مهمة يجب أن تملك:

```textgoal
success criteria
constraints
scope
time
```

---

# 329. Success Criteria

مثال:

```textApp launches
Tests pass
File exists
Git push succeeded
Presentation opens
```

---

# 330. Goal Completion

لا يتم:

```text"Looks good"
```

بل:

```textSuccess criteria satisfied
```

---

# 331. Final Result

الناتج النهائي يوضح:

```textWhat was requested
What was done
What was verified
What remains
Files created
Git state
```

---

# 332. Failure Reporting

إذا بعد استنفاد طرق الإصلاح لم يمكن تحقيق الهدف:

```textWhat failed
Why
What was attempted
Evidence
Last known state
Recommended next action
```

وليس:

> "حدث خطأ."

---

# 333. Partial Completion

إذا المهمة مركبة جدًا وتعذر جزء فعليًا، لا يخفي ذلك.

مثال:

```text80% complete
20% blocked by external system
```

لكن قبل إعلان ذلك يجب استنفاد بدائل الإصلاح المناسبة.

---

# 334. No Silent Success

أي نتيجة مهمة تحتاج evidence.

---

# 335. No Silent Destructive Action

حتى مع L4، الأفعال destructive يجب أن تكون:

> مرتبطة بالمهمة.

ليس:

> "أنا أستطيع لذلك فعلت."

---

# 336. Example of Correct Scope

> "نظّم ملفات المشروع داخل M:\Project."

يسمح:

```textM:\Project
```

لكن لا يسمح:

```textC:\RandomFolder
```

إلا إذا أصبحت مرتبطة بالمهمة.

---

# 337. Example of App Scope

> "افتح Blender وعدّل إعدادات المشروع."

يسمح:

```textBlender
Project files
Required browser research
```

ولا يفتح لعبة أو بريدًا عشوائيًا.

---

# 338. NEXUS Intelligence Hierarchy

```textUser
↓
Master Agent
↓
Orchestrator
↓
Specialists
↓
Tools
↓
Computer
```

---

# 339. Intelligence Infrastructure

```textModels
Memory
Retrieval
Research
Skills
Experience
```

---

# 340. Execution Infrastructure

```textWindows
Browser
Terminal
Files
Applications
Input
```

---

# 341. Reliability Infrastructure

```textVerification
Checkpoints
Recovery
Health
Audit
```

---

# 342. Extensibility Infrastructure

```textPlugins
MCP
Skills
Agents
Models
SDK
```

---

# 343. Final Core Systems

NEXUS في المنتج النهائي يتكون من:

```text1. UI
2. Desktop Launcher
3. Core Service
4. Master Agent
5. Orchestrator
6. Agent Runtime
7. Agent Registry
8. Tool Registry
9. Tool Router
10. Computer Runtime
11. Windows Runtime
12. Browser Runtime
13. Memory Engine
14. Learning Engine
15. Model Manager
16. Resource Manager
17. Verification Engine
18. Recovery Engine
19. Checkpoint Manager
20. Workspace Manager
21. Scope Engine
22. Permission Engine
23. Git Manager
24. GitHub Manager
25. Research Engine
26. Document Engine
27. Speech Engine
28. Vision Engine
29. Event Bus
30. Audit System
31. Plugin System
32. Skill System
33. Remote Gateway
34. NEXUS API
35. Evaluation System
```

---

# 344. Phase 0 — Foundation

المخرجات:

```textRepo
Build system
Config
Logging
SQLite
Events
Basic UI
Installer skeleton
```

---

# 345. Phase 1 — Core

```textTasks
Sessions
Workspace
Scope
Permissions
Lifecycle
```

---

# 346. Phase 2 — Tools

```textFiles
Terminal
System
Hardware
Git
```

---

# 347. Phase 3 — Local AI

```textllama.cpp
Model registry
Load/unload
Streaming
Benchmark
Resource checks
```

---

# 348. Phase 4 — Agent Runtime

```textMaster
Planner
Tool loop
Structured outputs
State
Context
```

---

# 349. Phase 5 — Memory

```textWorking memory
Task memory
Project memory
Workspace memory
User memory
Semantic retrieval
Compaction
```

---

# 350. Phase 6 — Windows Computer

```textWindows control
UIA
Mouse
Keyboard
Screen
Windows
Overlay
```

---

# 351. Phase 7 — Browser

```textBrowser sessions
Playwright
Browser Use
Downloads
Uploads
Web research
```

---

# 352. Phase 8 — Coding

```textCode index
Tree-sitter
Repo map
Coding agents
Build
Tests
Debug
Git
```

---

# 353. Phase 9 — Verification

```textAcceptance
Evidence
Repair
Test runners
Security
Performance
```

---

# 354. Phase 10 — Recovery

```textCheckpoints
Crash recovery
Restart recovery
Reconciliation
Scoped rollback
```

---

# 355. Phase 11 — Multi-Agent

```textAgent messaging
Ownership
Parallel execution
Subagents
Scheduling
```

---

# 356. Phase 12 — Learning

```textLessons
Skills
Workflow optimization
Prompt optimization
Skill creation
Learning sessions
```

---

# 357. Phase 13 — GitHub

```textSearch
Clone
Branch
Commit
Push
PR
Issues
Release
Secrets
```

---

# 358. Phase 14 — Documents/Speech/Vision

```textDocling
Speech engine
Vision engine
OCR where required
```

---

# 359. Phase 15 — Remote Web

```textRemote gateway
Realtime
Chat
Task control
File transfer
Computer view/control
Notifications
```

---

# 360. Phase 16 — Hardening

```textLong-run
Fault injection
Power loss
Network loss
Resource pressure
Security review
Performance
Packaging
```

---

# 361. Definition of Done — NEXUS

NEXUS لا يعتبر Finished عندما:

```textUI works
```

ولا عندما:

```textAgent calls tools
```

بل عندما ينجح في:

```textUnderstand
+
Plan
+
Execute
+
Observe
+
Verify
+
Repair
+
Persist
+
Recover
+
Learn
```

عبر:

```textFiles
Windows apps
Browser
Terminal
Code
GitHub
Documents
Long tasks
```

---

# 362. Product-level Definition of Done

يجب أن يستطيع المستخدم:

> "أعطيك الهدف، وتنجزه."

مع أقل تدخل ممكن.

وهذا هو جوهر المتطلبات الأصلية التي كتبتها: أن المنصة تفهم الهدف، تنفذ المشروع، تراجع نفسها، تصلح الأخطاء، تحفظ الحالة، وتستأنف العمل بعد الانقطاع.

---

# 363. Final Architecture

```text
                         ┌──────────────────────┐
                         │        USER          │
                         │ Text / Voice / Files │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      NEXUS UI        │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    MASTER AGENT      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────┐
                    │      NEXUS ORCHESTRATOR      │
                    │ Goal / Scope / Plan / State  │
                    └──────────────┬───────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        │                          │                           │
        ▼                          ▼                           ▼
┌───────────────┐          ┌────────────────┐          ┌────────────────┐
│ AGENT SYSTEM  │          │ MEMORY/LEARNING│          │ RESOURCE SYSTEM│
│               │          │                │          │                │
│ Planner       │          │ User           │          │ CPU            │
│ Research      │          │ Project        │          │ RAM            │
│ Coding        │          │ Workspace      │          │ GPU            │
│ Browser       │          │ Task           │          │ VRAM           │
│ Computer      │          │ Session        │          │ Concurrency    │
│ Testing       │          │ Lessons        │          └───────┬────────┘
│ Security      │          │ Skills         │                  │
│ Review        │          └───────┬────────┘                  │
└──────┬────────┘                  │                           │
       │                           │                           │
       └───────────────────────────┼───────────────────────────┘
                                   ▼
                          ┌──────────────────┐
                          │   TOOL ROUTER    │
                          └────────┬─────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
              Native            MCP             Plugins
               Tools             Tools             Tools
                  │                │                │
                  └────────────────┼────────────────┘
                                   ▼
                         ┌────────────────────┐
                         │ COMPUTER RUNTIME   │
                         ├────────────────────┤
                         │ Windows UI         │
                         │ Browser            │
                         │ Terminal           │
                         │ Filesystem         │
                         │ Mouse / Keyboard   │
                         │ Vision             │
                         │ Processes          │
                         └─────────┬──────────┘
                                   │
                                   ▼
                              WINDOWS PC
                                   │
                                   ▼
                          OBSERVE + VERIFY
                                   │
                       ┌───────────┴───────────┐
                       ▼                       ▼
                    SUCCESS                  REPAIR
                       │                       │
                       ▼                       └──────► EXECUTE
                  CHECKPOINT
                       │
                       ▼
                  MEMORY/LEARNING
                       │
                       ▼
                    CONTINUE
                       │
                       ▼
               FINAL VERIFICATION
                       │
                       ▼
                     RESULT
```

---

# 364. النموذج في الصورة النهائية

```text
                  NEXUS
                    │
          ┌─────────┴─────────┐
          │   MODEL MANAGER   │
          └─────────┬─────────┘
                    │
           ┌────────┼─────────┐
           ▼        ▼         ▼
         Tiny     Coder     Vision
           │        │         │
           └────────┼─────────┘
                    ▼
                llama.cpp
                    │
                    ▼
                 Local AI
```

النموذج ليس المدير.

**NEXUS Core هو المدير.**

---

# 365. النتيجة المعمارية الجوهرية

المشروع النهائي ليس:

```text1B model + tools
```

بل:

```text
Small Local Models
        +
Agent Harness
        +
Multi-Agent Runtime
        +
Memory
        +
Learning
        +
Retrieval
        +
Browser
        +
Windows Computer Control
        +
Tools
        +
Research
        +
Verification
        +
Recovery
        +
Git/GitHub
        +
Resource Management
        +
Remote Control
        +
Plugin System
```

---

# 366. الشكل النهائي للـNEXUS

يمكن تلخيصه:

```text
USER
  ↓
NEXUS
  ↓
MASTER AGENT
  ↓
ORCHESTRATOR
  ↓
AGENTS
  ↓
TOOLS
  ↓
COMPUTER
  ↓
RESULT
  ↑
VERIFY
  ↑
MEMORY
  ↑
LEARNING
  ↑
RECOVERY
```

---

# 367. القرارات النهائية المختصرة

## NEXUS Core
**نكتبه نحن.**

## Agent runtime
**نستفيد من Cline/ECC/LangGraph/Prime/Deep Agents كمرجعيات ومكونات عبر adapters.**

## Browser
**Browser Use + Playwright + Browser Harness حسب الحاجة.**

## Windows
**Windows Harness + UI Automation + pywinauto + native APIs.**

## Coding
**OpenHands/OpenCode/Cline + Aider concepts.**

## Memory
**NEXUS Memory Manager + SQLite + Mem0 + Qdrant.**

## Code intelligence
**Tree-sitter + repository graph + repo-map approach.**

## Documents
**Docling.**

## Speech
**sherpa-onnx/Whisper-family بعد benchmark حقيقي.**

## Local inference
**llama.cpp.**

## Tool protocol
**MCP.**

## Evaluation
**OSWorld + BrowserGym + custom NEXUS tests.**

## Remote
**NEXUS Remote Gateway، مع RustDesk/WebRTC كمرجع أو مكونات محددة بعد التحقق.**

---

# 368. ما يبقى ملك NEXUS

```text
NEXUS Core
NEXUS Task Model
NEXUS Scope
NEXUS Permission System
NEXUS Orchestrator
NEXUS Agent Registry
NEXUS Tool Registry
NEXUS Memory Manager
NEXUS Learning
NEXUS Resource Manager
NEXUS Verification
NEXUS Recovery
NEXUS Checkpoints
NEXUS Workspace Manager
NEXUS Window Manager
NEXUS Input Arbitration
NEXUS Plugin System
NEXUS Skill System
NEXUS Event System
NEXUS APIs
NEXUS Desktop UI
NEXUS Remote Protocol
```

---

# 369. معيار الاختيار لأي مكوّن مستقبلي

كلما ظهر Repo جديد نسأل:

```textDoes it solve a real NEXUS need?
Is it maintained?
Is the license compatible?
Does it work on Windows?
Does it work offline/local?
Can we isolate it behind an adapter?
Does it improve reliability?
Does it reduce implementation burden?
Does it introduce unacceptable dependency/security risk?
```

إذا كانت الإجابات مناسبة:

> يدخل.

---

# 370. معيار رفض Repo

نرفضه إذا:

- المشروع ميت.
- غير متوافق مع Windows.
- يعتمد على Cloud دون حاجة.
- ترخيصه غير مناسب.
- أمنيًا غير مناسب.
- لا يمكن عزله عن NEXUS.
- يفرض Architecture سيئة.
- يكرر وظيفة موجودة أفضل.
- عبء دمجه أكبر من فائدته.

---

# 371. المبدأ الأخير

NEXUS ليس سباقًا لإدخال أكبر عدد من Repositories.

هو:

> **أفضل منظومة ممكنة لتحقيق هدف المستخدم على جهازه.**

كل Repo مجرد قطعة.

**NEXUS هو النظام.**

---

# 372. الحالة المرجعية النهائية

**Product:** NEXUS  
**Platform:** Windows  
**Architecture:** Modular Super-Harness  
**AI:** Local-first, model-agnostic  
**Primary runtime:** llama.cpp  
**Core:** Custom NEXUS  
**Agents:** Multi-agent under Master Agent  
**Memory:** Multi-layer persistent  
**Learning:** Continuous, evidence-based  
**Computer Use:** Windows + Browser + Vision + UIA + input  
**Browser:** User + dedicated sessions  
**Coding:** Full lifecycle  
**GitHub:** First-class integration  
**Recovery:** Persistent checkpoints + reconciliation  
**Verification:** Independent and multi-layer  
**Remote:** Web client  
**Expansion:** Plugins + Skills + MCP + Models + Agents  
**Goal:** Autonomous completion of real digital work.

---

# 373. الخلاصة التنفيذية الأخيرة

NEXUS في شكله النهائي هو:

> **منصة ذكاء اصطناعي محلية مستقلة تشغّل نموذجًا صغيرًا أو مجموعة نماذج صغيرة، وتحيطها بطبقة Harness وOrchestrator وMemory وLearning وMulti-Agent وTools وComputer Use وBrowser وWindows Automation وVerification وRecovery وGit/GitHub وRemote Control، بحيث تستطيع تحويل هدف المستخدم إلى عمل رقمي حقيقي مكتمل على الكمبيوتر.**

الفرق الجوهري:

```text
Traditional AI:
Question → Answer

NEXUS:
Goal → Understand → Plan → Research → Execute → Observe → Verify → Repair → Remember → Learn → Continue → Finish
```

وهذا هو **التعريف الهندسي النهائي للمنتج الذي بنيناه في هذه المحادثة**، وليس تعريف Demo.

---

# 374. قائمة التحقق النهائية للخبراء

عند عرض المواصفة على خبير، يجب أن يراجع على الأقل:

```text[ ] Core architecture
[ ] Agent runtime
[ ] State machine
[ ] Scope model
[ ] Permission model
[ ] Windows control
[ ] Browser control
[ ] Computer vision
[ ] Input arbitration
[ ] Memory
[ ] Learning
[ ] Model routing
[ ] Resource management
[ ] Tool contracts
[ ] MCP
[ ] Plugin architecture
[ ] Skills
[ ] Large-codebase intelligence
[ ] Git/GitHub
[ ] Verification
[ ] Recovery
[ ] Checkpointing
[ ] Security
[ ] Secrets
[ ] Audit
[ ] Offline mode
[ ] Remote web
[ ] Database
[ ] APIs
[ ] Testing
[ ] Licensing
[ ] Packaging
[ ] Performance
[ ] Long-running stability
[ ] Future extensibility
```

---

# 375. المراجع التقنية الرئيسية المستخدمة في القرارات الحالية

**متطلبات NEXUS الأصلية:** 
**Cline SDK architecture:** separation بين shared/LLM/agents/core وstateful runtime/session/persistence.

**LangGraph:** stateful/resilient agent orchestration وreleases النشطة في 2026.

**Prime Agent:** persistent RLM/continual harness/subagents/skills/long-running/background execution.

**ECC:** agents/skills/hooks/rules/memory/verification/harness، مع ECC 2.0 في alpha بحسب توثيقه الحالي.

**OpenHands:** AI-driven development، core وagent-server تحت MIT مع استثناء enterprise.

**OpenCode:** coding agent مفتوح المصدر، MIT، مع subagent عام للمهام المعقدة.

**Aider:** repository map للـcodebase context.

**Browser Use:** browser agent infrastructure نشطة جدًا.

**Browser Harness:** self-healing editable CDP browser harness.

**Windows Harness:** Windows UIA + screen + input + browser + shell + filesystem، لكنه experimental.

**UI-TARS:** Computer-use research، GUI interaction، ونسخة Desktop محلية.

**Docling:** multi-format document processing مع PDF understanding وMIT codebase.

**Tree-sitter:** incremental parsing system مناسب لبناء code intelligence.

**sherpa-onnx:** local/offline speech recognition على Windows ومنصات متعددة.

**MCP SDKs:** Python v2 stable line وTypeScript v2 وفق مواصفة 2026-07-28.

**OSWorld-V2:** long-horizon Computer Use evaluation، مع release 2026.08.08 نشط.

**BrowserGym:** Web-agent research/evaluation framework مع عدة benchmarks.

**Trivy:** vulnerability/misconfiguration/secret/license scanning.

**Microsoft Agent Framework:** multi-agent workflows في Python و.NET ودعم Windows/local development.