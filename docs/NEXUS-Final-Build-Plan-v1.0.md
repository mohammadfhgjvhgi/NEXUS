# 0. تعليمات البناء الأساسية للوكيل

## 0.1 الهدف

ابنِ NEXUS على جهاز Windows الخاص بالمستخدم ليصبح **منتجًا نهائيًا حقيقيًا وقابلًا للاستخدام** وفق المواصفة الهندسية الرئيسية، وليس نسخة تجريبية.

يجب عدم اعتبار:

* واجهة تعمل
* Agent يرد
* Tool تعمل
* Browser يفتح
* نموذج يولد نصًا

دليلًا على اكتمال المشروع.

الاكتمال يعني أن النظام يحقق دورة:

```text
Prompt
→ Understanding
→ Scope
→ Planning
→ Delegation
→ Execution
→ Observation
→ Verification
→ Repair
→ Checkpoint
→ Memory
→ Learning
→ Continuation
→ Final Verification
→ Result
```

---

# 0.2 مبدأ بناء NEXUS

لا تعِد كتابة قدرات موجودة بكفاءة في المشاريع المفتوحة المصدر.

لا تقم أيضًا بدمج المستودعات بشكل عشوائي.

كل Repository يجب أن يمر بهذه الدورة:

```text
DISCOVER
↓
CLONE TO STAGING
↓
LICENSE AUDIT
↓
SECURITY REVIEW
↓
ARCHITECTURE REVIEW
↓
COMPATIBILITY REVIEW
↓
SELECT INTEGRATION MODE
↓
ADAPTER / EXTRACT / USE
↓
INTEGRATE INTO NEXUS
↓
TEST
↓
PIN VERSION/COMMIT
↓
DOCUMENT
```

---

# 0.3 قواعد Integration Modes

لكل Repository واحدة من الحالات:

### MODE A — DIRECT USE

يستخدم كمكتبة أو dependency مباشرة.

### MODE B — ADAPT

يستخدم لكن من خلال Adapter خاص بـNEXUS.

### MODE C — EXTRACT

يُستخرج منه جزء محدد فقط بعد مراجعة الترخيص والاعتماديات.

### MODE D — REFERENCE

يتم Clone إلى staging ودراسة architecture فقط، دون دخوله runtime.

### MODE E — TESTING ONLY

يستخدم في benchmark أو evaluation فقط.

### MODE F — REJECT

لا يدخل المنتج.

---

# 0.4 قاعدة حرجة

لا يجوز جعل NEXUS Core يعتمد مباشرة على classes أو internal APIs من Repository خارجي إذا كان يمكن وضع abstraction فوقه.

الصحيح:

```text
NEXUS Interface
↓
Adapter
↓
External Project
```

وليس:

```text
NEXUS Core
↓
External internal class
```

---

# 0.5 قاعدة الملكية

المكونات التالية يجب أن تبقى مملوكة لـNEXUS:

```text
Task system
Task state
Workspace
Scope
Permissions
Master Agent
Agent Registry
Tool Registry
Tool Router
Memory Manager
Learning Engine
Resource Manager
Model Manager
Verification Engine
Recovery Engine
Checkpoint Manager
Window Manager
Input Arbitration
Plugin System
Skill System
Event Bus
NEXUS APIs
Desktop UI
Remote API
```

لا يتم تفويض ملكية هذه الأجزاء بالكامل إلى Repository خارجي.

---

# 1. PHASE 0 — تجهيز الجهاز والمستودع الرئيسي

## الهدف

إنشاء البيئة التي سيُبنى عليها NEXUS قبل إدخال أي Agent أو Tool.

---

## 1.1 إنشاء GitHub Repository

المطلوب من الوكيل:

1. استخدام GitHub Token الذي يقدمه المستخدم.
2. إنشاء Repository خاص بـNEXUS.
3. اختيار اسم repository واضح مثل:

```text
nexus-platform
```

أو اسم يتفق مع اسم المنتج النهائي.

4. إنشاء branch رئيسي.
5. إنشاء branch تطوير.
6. تفعيل حماية الـmain إذا كان الحساب يسمح بذلك.
7. إنشاء `.gitignore`.
8. إنشاء `LICENSE`.
9. إنشاء `README`.
10. إنشاء `CONTRIBUTING`.
11. إنشاء `SECURITY`.
12. إنشاء `ARCHITECTURE`.
13. إنشاء `CHANGELOG`.

---

## 1.2 إنشاء Workspace محلي

يحدد المستخدم مكان المشروع، مثل:

```text
M:\NEXUS\
```

إذا اختار مسارًا آخر يستخدمه الوكيل.

البنية الأولية:

```text
M:\NEXUS\
├── nexus/
├── vendor-staging/
├── external/
├── build/
├── runtime/
├── models/
├── data/
├── docs/
├── tests/
└── backups/
```

---

## 1.3 إنشاء الهيكل البرمجي

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
├── workspace/
├── windows/
├── git/
├── github/
├── research/
├── documents/
├── speech/
├── vision/
├── plugins/
├── skills/
├── events/
├── resources/
├── security/
├── remote/
├── ui/
├── tests/
└── docs/
```

---

## 1.4 إنشاء CI

إضافة:

* unit tests
* lint
* type checking
* security checks
* packaging validation

ولا يتم merge إلى main من دون نجاح التحقق الأساسي.

---

# 2. PHASE 1 — NEXUS Core Foundation

## الهدف

إنشاء القلب الذي لا يعتمد على أي Agent Framework خارجي كهوية أساسية.

---

## 2.1 Core Configuration

أنشئ:

```text
config/
├── system
├── models
├── tools
├── agents
├── workspaces
└── security
```

المخرجات:

* typed configuration
* environment resolution
* local paths
* runtime configuration

---

## 2.2 Event Bus

أنشئ Event Bus مركزي.

الأحداث الأساسية:

```text
system.started
task.created
task.started
task.updated
task.paused
task.resumed
task.completed

agent.started
agent.completed
agent.failed

tool.called
tool.completed
tool.failed

model.loading
model.loaded
model.unloaded
model.error

window.opened
window.closed

checkpoint.created
recovery.started
recovery.completed

verification.started
verification.passed
verification.failed

memory.created
memory.updated
learning.created
```

---

## 2.3 Session System

أنشئ:

```text
Session
Conversation
Task
```

ولا تخلط بينها.

الهرمية:

```text
User
 └── Conversation
      └── Task
           └── Session
```

---

## 2.4 Task Engine

أنشئ Task State Machine:

```text
CREATED
ANALYZING
CLARIFICATION_REQUIRED
PLANNING
EXECUTING
VERIFYING
REPAIRING
WAITING_NETWORK
WAITING_RESOURCE
RECOVERING
PAUSED
COMPLETED
CANCELLED
```

---

## 2.5 Task Persistence

كل Task تحفظ:

* Goal
* Prompt
* Scope
* Workspace
* Plan
* Agents
* State
* Checkpoints
* Errors
* Verification
* Result

---

## 2.6 Exit Criteria

لا تنتقل:

* إلا إذا Task يمكن إنشاؤها.
* حفظها.
* إغلاق NEXUS.
* فتحه.
* استرجاع Task.
* متابعة state.

---

# 3. PHASE 2 — Workspace + Scope + Policy

## الهدف

تثبيت المفهوم الذي وصفته أنت:

> Full Control within Task Scope.

---

## 3.1 Workspace Manager

أنشئ Workspace object:

```text
id
name
path
project
memory_namespace
git_repository
settings
```

---

## 3.2 Scope Engine

الـScope يحتوي:

```text
filesystem paths
applications
browser sessions
network permissions
tools
repositories
```

---

## 3.3 Scope Resolution

مثال:

```text
"اشتغل على M:\Client"

→ workspace = Client
→ filesystem scope = M:\Client
```

---

## 3.4 Cross-workspace Access

لا تمنع الوصول مطلقًا.

إذا المهمة تقول:

> "خذ قرار authentication من المشروع الثاني"

يبحث في workspace الآخر فقط عن الجزء المطلوب.

---

## 3.5 Policy Engine

أنشئ Task Policy:

```text
autonomy_level
time_policy
network_policy
tool_policy
workspace_scope
app_scope
git_policy
external_ai_policy
resource_policy
```

---

# 4. PHASE 3 — Hardware Intelligence + Resource Manager

## الهدف

اجعل NEXUS يعرف الجهاز بنفسه ويعمل ضمن قدراته.

---

## 4.1 Hardware Scanner

يكتشف:

```text
CPU
GPU
VRAM
RAM
Storage
Displays
Resolution
Windows
Network
Devices
Installed software
Processes
```

---

## 4.2 Hardware Profile

يحفظ:

```text
hardware_profile
```

ولا يعتمد على model memory.

هذه **بيانات نظام**.

---

## 4.3 Change Detection

يقارن:

```text
Previous profile
vs
Current profile
```

ويكتشف:

* RAM changed
* GPU changed
* Storage changed
* display changed
* drivers/runtime changes where detectable

---

## 4.4 Resource Manager

يتابع:

```text
CPU
RAM
GPU
VRAM
Disk
concurrency
model memory
agent count
```

---

## 4.5 Resource Policies

مثال:

```text
RAM pressure
→ reduce concurrency

VRAM pressure
→ unload model / switch

CPU pressure
→ reduce background work
```

المبدأ:

> نخفض السرعة قبل أن نخسر المهمة.

---

## 4.6 Repo/Reference

هذه المرحلة تعتمد أساسًا على Windows APIs/system libraries.

Repositories مساعدة لاحقًا:

* Windows SDK
* Windows App SDK
* System information libraries

هذه المرحلة لا تحتاج framework Agent.

---

# 5. PHASE 4 — Local Model Runtime

## الهدف

إدخال الذكاء المحلي إلى NEXUS.

---

## 5.1 Model Abstraction

أنشئ Interface:

```text
ModelProvider
├── load
├── unload
├── generate
├── stream
├── health
├── capabilities
└── benchmark
```

---

## 5.2 Model Registry

لكل Model:

```text
id
name
format
backend
size
context
capabilities
ram
vram
language
benchmark
status
```

---

## 5.3 llama.cpp Integration

Repository:

**ggml-org/llama.cpp**

الدور:

> Primary local inference backend.

المشروع حاليًا نشط جدًا، ويحتوي `llama-server` ويدعم local inference وLLM/VLM workflows. ([github.com](https://github.com/ggml-org/llama.cpp))

الطريقة:

```text
NEXUS Model API
↓
llama.cpp Adapter
↓
llama-server
↓
Model
```

---

## 5.4 Dynamic Loading

يجب تنفيذ:

```text
select
load
run
keep warm
unload
```

بحسب الموارد.

---

## 5.5 Model Benchmarking

عند تسجيل Model:

```text
warmup
prompt speed
generation speed
context
RAM
VRAM
stability
```

ثم يحفظ benchmark.

---

## 5.6 MiMo Edge Profile

أضف نتائج اختبارات جهاز المستخدم كـinitial benchmark baseline:

```text
Qwen2.5-Coder-1.5B
LFM2.5-1.2B
Qwen3-0.6B
DS-Coder-1.3B
Yi-Coder-1.5B
```

لكن لا تجعل هذه القائمة ثابتة.

هي أول Model Pool فقط.

---

## 5.7 Model Router

Input:

```text
Task type
Complexity
Required capability
RAM
VRAM
Current workload
```

Output:

```textselected model id
```

---

# 6. PHASE 5 — Agent Runtime

## الهدف

تحويل model إلى Agent فعلي.

---

## 6.1 Agent abstraction

كل Agent:

```text
Agent
├── id
├── role
├── instructions
├── capabilities
├── tools
├── memory policy
├── model policy
└── verification
```

---

## 6.2 Agent Loop

التنفيذ:

```text
Observe
→ Context
→ Decide
→ Tool/Agent call
→ Observe
→ Verify
→ Continue
```

---

## 6.3 Master Agent

Master Agent:

* يتعامل مع المستخدم.
* يفهم الهدف.
* يوزع العمل.
* يتابع Agents.
* يستقبل النتائج.
* يقرر الاستمرار.
* يقرر الوصول إلى Verification.

---

## 6.4 Agent Registry

دعم:

```textregisterAgent
unregisterAgent
discoverAgents
getCapabilities
```

---

## 6.5 Agent Communication

structured messages:

```text
task_id
sender
receiver
type
status
data
evidence
confidence
```

---

## 6.6 Agent Ownership

يحدد:

```textresource
owner
```

لمنع Agentين من تعديل نفس الملف أو المورد بلا تنسيق.

---

# 7. PHASE 6 — Harness Integration

## الهدف

إدخال أفضل patterns من Harness ecosystems.

---

## 7.1 ECC

Repository:

**affaan-m/ecc**

الدور:

> Harness patterns.

نستخرج/نقتبس:

* Skills structure
* Rules
* Hooks
* Agent specialization
* Verification patterns
* Memory patterns
* Research workflows
* Security patterns

ECC حاليًا يحتوي منظومة واسعة من agents/skills/hooks/rules/memory ويستمر في التطور، مع ECC 2.0 موصوف في توثيقه الحالي كمسار alpha. ([github.com](https://github.com/affaan-m/ecc?utm_source=chatgpt.com))

**Integration mode:**

```text
CLONE → REVIEW → ADAPT
```

لا تضع ECC بالكامل داخل NEXUS.

---

## 7.2 Cline SDK

Repository:

**cline/cline**

الدور:

> Agent runtime architecture reference/component candidate.

ادرس:

```text
shared
llms
agents
core
```

لأن architecture الحالية تفصل فعلًا بين الـagent loop والـstateful core والـLLM abstraction.

استخدم خصوصًا:

* session lifecycle patterns
* tool system
* events
* plugin architecture
* stateful runtime

**Integration: ADAPT.**

---

## 7.3 LangGraph

Repository:

**langchain-ai/langgraph**

الدور:

> Orchestration + persistence.

استخدم:

* graph execution
* state
* checkpoints
* recovery patterns
* subgraphs
* durability

LangGraph يحفظ graph state عبر checkpointers ويمكنه دعم fault-tolerant execution وtime travel وmemory؛ كما أن لديه عدة durability modes.

**Integration: USE/ADAPT.**

---

## 7.4 Prime Agent

Repository:

**PrimeIntellect-ai/prime-agent**

الدور:

> Long-horizon / continual execution reference.

استخرج:

* goals
* persistent sessions
* heartbeats
* schedules
* continual harness
* memories
* skills
* subagents
* refinement

Prime Agent حاليًا يذكر صراحةً persistent goals، heartbeats/schedules، daemon-backed continuity، continual harness وagent-to-agent communication.

**Integration: REFERENCE/ADAPT.**

---

## 7.5 Deep Agents

Repository:

**langchain-ai/deepagents**

الدور:

> deep-agent pattern / subagents / skills / backends.

**Integration: REFERENCE/ADAPT.**

---

# 8. PHASE 7 — Tool System

## الهدف

كل capability تدخل NEXUS كـTool موحدة.

---

## 8.1 Tool Registry

كل Tool:

```text
id
name
description
input_schema
output_schema
permissions
scope_requirements
risk
verification
version
```

---

## 8.2 Tool Router

```text
Agent
→ Tool discovery
→ Permission
→ Scope
→ Resource
→ Execute
→ Normalize result
→ Verify
```

---

## 8.3 Native Tools

ابنِ:

```text
filesystem
terminal
process
hardware
windows
clipboard
screen
git
github
```

---

## 8.4 MCP

Repository:

**modelcontextprotocol**

الدور:

> Interoperability layer.

استخدم SDK الرسمي حسب اللغة التي سيستقر عليها جزء NEXUS.

Python SDK الحالي هو v2 stable line ويدعم tools/resources/prompts وstdio وStreamable HTTP وSSE؛ TypeScript SDK الحالي أيضًا ضمن v2. ([github.com](https://github.com/modelcontextprotocol/python-sdk?utm_source=chatgpt.com))

**Integration: USE behind NEXUS Tool Router.**

---

## 8.5 MCP Servers

Clone فقط الذي تحتاجه المهمة/القدرة:

```text
filesystem
git
fetch
memory
database
```

لكن كل واحد يمر عبر:

```text
NEXUS permission
NEXUS scope
```

---

# 9. PHASE 8 — Windows Computer Runtime

## الهدف

جعل NEXUS قادرًا على استخدام الكمبيوتر الحقيقي.

---

## 9.1 Computer API

أنشئ:

```text
screens
windows
focus
mouse
keyboard
clipboard
uia
processes
```

---

## 9.2 Windows Harness

Repository:

**browser-use/windows-harness**

الدور:

> primary experimental Windows automation backend.

المشروع الحالي يجمع Windows UI Automation، screenshots، mouse/keyboard input، browser، Python، PowerShell وfilesystem، مع بنية tests وSECURITY، لكنه ما زال Experimental.

**Integration: ADAPT BEHIND COMPUTER API.**

لا تجعل NEXUS dependent مباشرة على تفاصيله الداخلية.

---

## 9.3 pywinauto

Repository:

**pywinauto**

الدور:

> Windows UI Automation backend.

استخدمه لـ:

* Win32
* UI Automation
* controls
* mouse/keyboard
* text extraction

**Integration: USE/ADAPT.**

---

## 9.4 Windows UI Automation

استخدم native Windows UIA كطبقة أولى حيثما أمكن.

---

## 9.5 Computer Use Fallback Hierarchy

رتب التحكم:

```text
Application API
↓
Windows UI Automation
↓
Browser DOM / Accessibility
↓
Vision
↓
Mouse/Keyboard
```

---

# 10. PHASE 9 — Window Manager + Human Parallelism

## الهدف

تحقيق فكرتك التي وصفتها عن:

> أنت تستخدم جهازك وNEXUS يعمل في مكان آخر في نفس الوقت.

---

## 10.1 Window Registry

كل نافذة:

```text
window_id
application
task_id
workspace
agent
position
size
visibility
input_owner
```

---

## 10.2 Window Ownership

مثال:

```text
War Thunder → USER
Chrome A → USER
Chrome B → NEXUS
PowerPoint → NEXUS
```

---

## 10.3 Human/AI Input Arbitration

NEXUS يميز بين:

```text
Human-owned window
AI-owned window
Shared window
```

---

## 10.4 Multiple Monitors

يجب أن يعرف:

```text
monitor list
resolution
position
window placement
```

---

## 10.5 Overlay

عند Computer Use:

```text
NEXUS is working
[Pause]
[Resume]
```

شفاف وبسيط.

---

# 11. PHASE 10 — Browser Runtime

## الهدف

إعطاء NEXUS Browser capability كاملة.

---

## 11.1 Playwright

Repository:

**microsoft/playwright**

الدور:

> Browser execution engine.

يستخدم لـ:

* navigation
* DOM
* forms
* upload
* download
* tabs
* browser states
* automation

Playwright يدعم Chromium وFirefox وWebKit، ويعمل على Windows، كما لديه Playwright MCP tooling. ([github.com](https://github.com/microsoft/playwright?utm_source=chatgpt.com))

**Integration: USE.**

---

## 11.2 Browser Use

Repository:

**browser-use/browser-use**

الدور:

> Browser agent layer.

يستخدم لـ:

* browser reasoning
* agent actions
* persistent browser workflows
* browser task execution

**Integration: ADAPT/USE.**

---

## 11.3 Browser Harness

Repository:

**browser-use/browser-harness**

الدور:

> self-healing/editable browser harness.

المشروع يتعامل مع Chrome عبر CDP ويقدم أدوات مثل tabs/navigation/click/type/upload/screenshot وغيرها. ([github.com](https://github.com/browser-use/browser-harness?utm_source=chatgpt.com))

**Integration: ADAPT.**

---

## 11.4 Browser Sessions

دعم:

```text
User session
Agent session
```

ويجب ألا تختلط بياناتهما دون قصد.

---

## 11.5 Authentication

يمكن NEXUS استخدام authorized browser sessions.

الـcredentials لا تظهر في:

```text
memory
logs
normal events
```

---

# 12. PHASE 11 — Vision + OCR + Screen Understanding

## الهدف

إعطاء NEXUS القدرة البصرية التي تحتاجها التطبيقات التي لا تقدم UI structure مفيدة.

---

## 12.1 Screen Capture

ابنِ layer تدعم:

```text
full screen
window
region
```

---

## 12.2 Vision Adapter

```text
VisionProvider
├── analyze
├── locate
├── classify
└── compare
```

---

## 12.3 UI-TARS

Repository:

**bytedance/UI-TARS**

الدور:

> Research/reference for GUI agent vision and action.

لا تجعله النموذج الأساسي لجهازك الحالي.

**Integration: REFERENCE/BENCHMARK.**

---

## 12.4 Computer Use Research

Clone للاختبار/الدراسة:

```text
UI-TARS
OpenCUA
Agent-S
```

لكن لا تدخلها كلها إلى production runtime.

---

## 12.5 OCR

اختيار OCR النهائي يجب أن يتم بالـbenchmark على جهازك.

المطلوب:

```textArabic
English
numbers
UI labels
documents
```

---

# 13. PHASE 12 — Memory System

## الهدف

إنشاء الذاكرة التي تمنع فقدان السياق.

---

## 13.1 Memory Manager

أنشئ abstraction:

```textremember
retrieve
search
update
forget
summarize
link
```

---

## 13.2 Memory hierarchy

```text
GLOBAL
USER
PROJECT
WORKSPACE
TASK
SESSION
AGENT
KNOWLEDGE
DECISION
LESSON
SKILL
ERROR
```

---

## 13.3 SQLite

استخدم SQLite للـstructured state:

```text
tasks
sessions
workspaces
events
agents
tools
models
checkpoints
permissions
hardware
settings
```

---

## 13.4 Mem0

Repository:

**mem0ai/mem0**

الدور:

> persistent memory engine candidate.

Mem0 يركز على memory layer للـagents مع User/Session/Agent memory ومتكامل مع agent frameworks. ([github.com](https://github.com/mem0ai/mem0?utm_source=chatgpt.com))

**Integration: USE/ADAPT.**

---

## 13.5 Qdrant

Repository:

**qdrant/qdrant**

الدور:

> semantic/vector retrieval.

**Integration: USE.**

---

## 13.6 Memory Retrieval

لا تسترجع كل الذاكرة.

Pipeline:

```text
Prompt
→ Task
→ Workspace
→ Relevant memories
→ Relevant knowledge
→ Context
```

---

## 13.7 Memory Conflict Resolution

إذا:

```textold preference
vs
new explicit instruction
```

الجديد يفوز.

---

# 14. PHASE 13 — Learning System

## الهدف

جعل NEXUS يتعلم من العمل وليس فقط "يتذكر".

---

## 14.1 Experience Extractor

من كل مهمة استخرج:

```text
success patterns
failures
lessons
decisions
preferences
skills
```

---

## 14.2 Confidence System

لكل lesson:

```text
source
evidence
confidence
scope
```

---

## 14.3 Learning Levels

```text
Memory
↓
Lesson
↓
Skill
↓
Workflow improvement
↓
Prompt optimization
↓
Model optimization
↓
Fine-tuning
```

---

## 14.4 Skill Creation

```textRepeated workflow
↓
Candidate skill
↓
Test
↓
Verify
↓
Register
```

---

## 14.5 Letta Code

Repository:

**letta-ai/letta-code**

الدور:

> reference لـpersistent agent identity والmemory والskills.

**Integration: REFERENCE.**

---

## 14.6 Prime Continual Harness

استخدم concepts الخاصة بـ:

* persistent lessons
* memories
* skills
* subagent specs

Prime يطبق بالفعل continual harness يفصل reusable state عن token history.

---

## 14.7 DSPy

Repository:

**stanfordnlp/dspy**

الدور:

> optional optimization layer.

استخدم لاحقًا في:

* prompt optimization
* workflow optimization
* evaluation-driven refinement

**Integration: REFERENCE/POSSIBLE USE.**

---

# 15. PHASE 14 — Coding Intelligence

## الهدف

جعل NEXUS قادرًا على بناء وصيانة مشاريع ضخمة.

---

## 15.1 Tree-sitter

Repository:

**tree-sitter/tree-sitter**

الدور:

> parsing / AST / incremental code analysis.

**Integration: USE.**

---

## 15.2 Repository Indexer

أنشئ:

```text
file index
symbol index
AST
dependency graph
API graph
test graph
architecture map
```

---

## 15.3 Repo Map

استفد من فكرة Aider.

Repository:

**Aider-AI/aider**

الدور:

> reference / extraction لـcodebase mapping.

Aider يبني repo map للمشروع ويستخدمه لاختيار السياق المهم بدل تحميل كل الكود للـLLM. ([github.com](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md?utm_source=chatgpt.com))

---

## 15.4 Large Repository Context

المطلوب:

```text
400k lines
↓
Index
↓
Map
↓
Relevant retrieval
↓
Focused context
```

---

## 15.5 Coding Agents

### OpenHands

الدور:

> coding agent architecture.

### OpenCode

الدور:

> coding agent/runtime/client-server reference.

### Cline

الدور:

> agent loop / SDK / tools / session.

---

## 15.6 Coding Flow

```text
Analyze
→ Architecture
→ Edit
→ Build
→ Test
→ Diagnose
→ Fix
→ Retest
→ Security
→ Review
→ Commit
```

---

# 16. PHASE 15 — Git and GitHub

## الهدف

جعل GitHub جزءًا من دورة المشروع.

---

## 16.1 Git Engine

Native Git CLI/library.

وظائف:

```text
status
diff
branch
worktree
commit
merge
tag
rollback
```

---

## 16.2 GitHub Engine

وظائف:

```text
search
repo
clone
pull
push
branch
PR
issues
releases
```

---

## 16.3 Git Checkpoints

عند milestones:

```text
checkpoint
→ commit
```

لكن ليس كل checkpoint يجب أن يعمل push.

---

## 16.4 Branch Policy

```text
Small task
→ current branch

Major feature
→ feature branch

Parallel work
→ isolated worktrees

Risky operation
→ checkpoint + branch
```

---

## 16.5 GitHub Token

يجب تخزين reference وليس secret plain-text داخل memory.

---

# 17. PHASE 16 — Research Engine

## الهدف

تحويل NEXUS إلى Research Agent قوي.

---

## 17.1 Search abstraction

```text
Web
GitHub
Docs
Forums
Academic
Local files
```

---

## 17.2 Search pipeline

```text
Query
→ Search
→ Collect
→ Deduplicate
→ Rank
→ Verify
→ Extract
→ Store evidence
```

---

## 17.3 Research Agent

المهام:

* source discovery
* comparison
* source evaluation
* technical investigation
* GitHub discovery

---

## 17.4 External AI Consultation

Tool رسمية:

```text
consult_external_ai()
```

المسار:

```text
Local reasoning insufficient
→ research
→ external AI consultation
→ compare
→ verify
→ use
```

---

# 18. PHASE 17 — Document Intelligence

## الهدف

تمكين NEXUS من Word/PDF/PPTX والوثائق.

---

## 18.1 Docling

Repository:

**docling-project/docling**

الدور:

> document ingestion/parsing.

يدعم حاليًا صيغًا متعددة مثل PDF وDOCX وPPTX وXLSX وHTML وغيرها. ([github.com](https://github.com/docling-project/docling?utm_source=chatgpt.com))

**Integration: USE.**

---

## 18.2 Document workflow

```text
File
→ Parse
→ Structure
→ Retrieve
→ Modify
→ Verify
```

---

## 18.3 Word

يجب أن يدعم:

```text
open
create
edit
format
save
verify
```

---

## 18.4 PowerPoint

```text
create
slides
images
sources
format
review
save
verify
```

---

# 19. PHASE 18 — Speech System

## الهدف

تحويل الصوت إلى Prompt دقيق.

---

## 19.1 Speech Pipeline

```text
Microphone
→ VAD
→ Speech-to-text
→ Language detection
→ normalization
→ Prompt
```

---

## 19.2 sherpa-onnx

Repository:

**k2-fsa/sherpa-onnx**

الدور:

> local/offline speech recognition candidate.

المشروع يدعم التشغيل المحلي دون إنترنت وWindows. ([github.com](https://github.com/k2-fsa/sherpa-onnx?utm_source=chatgpt.com))

---

## 19.3 Arabic Benchmark

اختبارات:

```text
Arabic colloquial
Arabic technical
English technical
Arabic+English mixed
fast speech
noisy environment
```

---

# 20. PHASE 19 — Verification Engine

## الهدف

منع NEXUS من قول "خلصت" دون دليل.

---

## 20.1 Verification abstraction

```text
Verifier
├── Software
├── Browser
├── Windows
├── Document
├── Research
├── Git
└── System
```

---

## 20.2 Evidence

كل verification تنتج:

```text
criterion
method
result
evidence
timestamp
```

---

## 20.3 Software Verification

```text
compile
unit
integration
e2e
lint
types
security
performance
```

---

## 20.4 Browser Verification

```text
URL
DOM
state
download
upload
expected output
```

---

## 20.5 Windows Verification

```text
window
application
UI
process
file
output
```

---

# 21. PHASE 20 — Security System

## الهدف

Full capability دون Full chaos.

---

## 21.1 Scope

ما الذي ترتبط به المهمة؟

---

## 21.2 Permission

ما الأدوات المسموحة؟

---

## 21.3 Execution Gate

هل العملية مسموحة في هذه اللحظة؟

---

## 21.4 Credential Vault

يخزن:

```text
GitHub tokens
API keys
browser credentials
external AI credentials
```

ويعطي agents references.

---

## 21.5 Secret redaction

أمنع الأسرار من:

```text
chat
memory
logs
errors
events
```

---

## 21.6 Security Tools

### Trivy

Repository:

**aquasecurity/trivy**

الدور:

* vulnerabilities
* secrets
* dependencies
* licenses
* configuration

**Integration: USE where applicable.**

---

## 21.7 Semgrep

استخدم للـstatic analysis عند الحاجة.

---

## 21.8 Pyright

للمشاريع Python.

---

# 22. PHASE 21 — Recovery + Checkpoints

## الهدف

ضمان عدم ضياع المهمة.

---

## 22.1 Checkpoint Types

```text
State checkpoint
Task checkpoint
Project checkpoint
Git checkpoint
```

---

## 22.2 Checkpoint triggers

```text
task start
phase complete
major change
before risky operation
after critical test
periodic interval
```

---

## 22.3 Recovery

```text
Crash
→ detect
→ load checkpoint
→ inspect filesystem
→ inspect processes
→ inspect Git
→ reconcile
→ resume
```

---

## 22.4 Actual State Wins

مثال:

```text
Saved state:
file exists

Actual filesystem:
file missing
```

الحقيقة الحالية تفوز.

---

## 22.5 LangGraph

استفد من checkpointer/durable execution patterns؛ LangGraph يدعم checkpoints لكل super-step، threads، persistence، time travel وfault tolerance.

---

## 22.6 Prime Agent

استفد من:

* heartbeat
* persistent goals
* detached sessions
* reattach
* continual harness

كمرجع للـlong-running runtime.

---

# 23. PHASE 22 — Heartbeat + Stall Detection

## الهدف

لا يعلق NEXUS بصمت وأنت بعيد عن الكمبيوتر.

---

## 23.1 Heartbeat

راقب:

```text
core
worker
agent
tool
model
browser
computer runtime
```

---

## 23.2 Stall detection

اكتشف:

```text
same state
same action
same error
no meaningful progress
```

---

## 23.3 Recovery path

```text
stall
→ diagnose
→ retry
→ alternate method
→ replan
→ recover
```

---

# 24. PHASE 23 — Multi-Agent Orchestration

## الهدف

تشغيل عدة Agents دون فوضى.

---

## 24.1 Master

```text
Master
```

---

## 24.2 Specialist agents

```text
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

---

## 24.3 Parallel execution

المسموح عندما:

```text
tasks independent
resources independent
files independent
```

---

## 24.4 Agent coordination

كل Agent يعرف:

```text
parent
children
task
scope
owned resources
```

---

# 25. PHASE 24 — Long-Horizon Execution

## الهدف

الوصول إلى ما وصفته:

> أعطيه المهمة وأذهب.

---

## 25.1 Long task manager

يدعم:

```text
hours
days
```

---

## 25.2 Task deadline

يدعم:

```text
30 minutes
2 hours
8 hours
until completion
```

---

## 25.3 Background execution

NEXUS Core يستمر حتى لو أغلقت UI.

---

## 25.4 Task heartbeat

كل مهمة طويلة لديها monitoring.

---

## 25.5 Automatic continuation

بعد كل milestone:

```text
checkpoint
→ continue
```

---

# 26. PHASE 25 — Desktop UI

## الهدف

واجهة عملية تشبه الأدوات التي تستخدمها، وليست لوحة مصطنعة.

---

## 26.1 Main window

```text
Sidebar
Conversation list

Main
Chat

Bottom
Prompt
Voice
Attachment
```

---

## 26.2 Capability profiles

```text
Full Stack
Android
Coding
Research
Automation
Computer
Documents
```

لكن الاختيار لا يقفل بقية القدرات.

---

## 26.3 Activity

```text
Planner → Working
Research → Searching
Browser → Opened
Coder → Editing
Tester → Testing
```

---

## 26.4 Detailed activity

عند فتح التفاصيل:

```text
agent
tool
target
result
verification
```

---

## 26.5 Checkpoint History

```text
Task
├── Checkpoint 1
├── Checkpoint 2
├── Checkpoint 3
```

مع:

```text
date
phase
result
```

---

# 27. PHASE 26 — Desktop Tray + Startup

## الهدف

NEXUS يبدأ مع Windows دون إزعاج.

---

## 27.1 Startup

```text
Windows
→ NEXUS Launcher
→ Core
```

---

## 27.2 Tray

الحالة:

```text
Ready
Working
Waiting
Recovering
Error
```

---

## 27.3 Tray actions

```text
Open
Pause current task
Resume
View tasks
Exit safely
```

---

# 28. PHASE 27 — Remote Web

## الهدف

تحويل الهاتف إلى Remote Client فقط.

---

## 28.1 Frontend

HTML5/CSS/JS.

يمكن استضافته على GitHub Pages.

---

## 28.2 لا تضع Core على GitHub Pages

GitHub Pages:

```text
UI only
```

NEXUS PC:

```text
Core
Agents
Models
Tools
Memory
Computer
```

---

## 28.3 Remote protocol

```text
chat
tasks
events
file transfer
control
notifications
```

---

## 28.4 Realtime

افصل:

```text
Control channel
Event channel
Screen/video channel
```

---

## 28.5 File retrieval

الهاتف:

> "جيبلي التقرير."

NEXUS:

```text
locate
scope-check
prepare
transfer
download
```

---

## 28.6 Computer remote view

المطلوب النهائي:

> remote live interaction

وليس مجرد screenshot دوري.

---

# 29. PHASE 28 — Remote Security

## الهدف

منع أي شخص غير مصرح له من الوصول.

---

## 29.1 Device registration

الـPC يسجل الجهاز المسموح له.

---

## 29.2 Remote session

كل جلسة:

```text
session_id
device
authorization
expires
```

---

## 29.3 Permissions

الـremote client لا يتجاوز صلاحيات NEXUS نفسه.

---

# 30. PHASE 29 — Plugin System

## الهدف

إضافة القدرات دون تعديل Core.

---

## 30.1 Plugin manifest

```text
name
version
type
permissions
dependencies
entrypoints
```

---

## 30.2 أنواع Plugins

```text
Agent
Tool
Skill
Model
MCP
Integration
UI
```

---

## 30.3 Plugin lifecycle

```text
discover
validate
install
register
enable
disable
update
remove
```

---

# 31. PHASE 30 — Skill System

## الهدف

إدارة المهارات المكتسبة.

---

## 31.1 Skill schema

```text
id
name
description
inputs
tools
workflow
verification
version
```

---

## 31.2 Skill source

يمكن أن تأتي من:

```text
manual
learned
plugin
imported
generated
```

---

## 31.3 Skill verification

لا يتم تثبيت Skill generated مباشرة.

```text
candidate
→ test
→ validate
→ install
```

---

# 32. PHASE 31 — Model Learning / Fine-tuning

## الهدف

إتاحة تطوير النموذج لاحقًا.

---

## 32.1 Dataset collector

يجمع:

```text
successful interactions
failed interactions
corrections
verified outputs
```

---

## 32.2 Dataset hygiene

لا تدخل:

```text
secrets
credentials
private files
unreviewed hallucinations
```

---

## 32.3 Evaluation first

قبل fine-tuning:

```textbaseline
→ train
→ benchmark
→ compare
→ accept/reject
```

---

# 33. PHASE 32 — Computer Use Evaluation

## OSWorld-V2

Repository:

**xlang-ai/OSWorld-V2**

الدور:

> external Computer Use evaluation.

الإصدار الحالي الذي ظهر في البحث هو `osworld-v2-2026.08.08`، ويتضمن تحديثات لإصلاح reward-hacking وتحسين robustness/fairness.

يستخدم كـevaluation harness، وليس runtime dependency.

---

# 34. PHASE 33 — Browser Evaluation

## BrowserGym

استخدمه لتقييم:

```text
navigation
forms
research
downloads
web interaction
```

ولا تدخله إلى NEXUS runtime.

---

# 35. PHASE 34 — Full System Verification

## الاختبار الأول: Chat

```text
Arabic
English
mixed
```

---

## الاختبار الثاني: Voice

```text
Arabic command
English technical command
mixed
```

---

## الاختبار الثالث: Files

```text
create
read
edit
move
copy
delete
```

ضمن Scope.

---

## الاختبار الرابع: Windows

```text
launch app
interact
close
verify
```

---

## الاختبار الخامس: Browser

```text
open
search
click
type
download
upload
verify
```

---

## الاختبار السادس: Word

```text
open Word
create document
insert content
format
save
verify
```

---

## الاختبار السابع: PowerPoint

```text
create
research
images
sources
format
verify
```

---

## الاختبار الثامن: GitHub

```text
clone
branch
edit
commit
push
PR
```

---

## الاختبار التاسع: Large repository

```text
300k+
index
map
understand
modify
test
```

---

## الاختبار العاشر: Multi-agent

```text
plan
research
code
test
review
```

بالتوازي عند الإمكان.

---

# 36. PHASE 35 — Failure Injection

اختبر:

```text
internet lost
model crash
browser crash
tool failure
process crash
NEXUS restart
Windows restart
power interruption simulation
disk low
RAM pressure
VRAM pressure
Git conflict
bad external answer
```

---

# 37. PHASE 36 — Recovery Validation

لكل failure:

```text
failure
→ detect
→ checkpoint
→ restore
→ reconcile
→ continue
→ verify
```

---

# 38. PHASE 37 — Final Security Audit

تحقق:

```text
scope enforcement
credential handling
secret redaction
tool permissions
plugin permissions
MCP permissions
remote authorization
filesystem boundaries
```

---

# 39. PHASE 38 — Performance Optimization

## الهدف

NEXUS لا يستهلك الجهاز وهو idle.

---

## 39.1 Idle mode

```text
Core running
Heavy models unloaded
Workers minimized
```

---

## 39.2 Active mode

تشغيل فقط المطلوب.

---

## 39.3 Memory optimization

```text
context compaction
tool output compression
memory retrieval
model unloading
```

---

# 40. PHASE 39 — Production Packaging

## Windows Installer

يجب أن يثبت:

```text
NEXUS
Core
Launcher
UI
required runtimes
```

---

## Model setup

خلال first-run:

```text
hardware scan
model selection
download/install
benchmark
```

---

## Dependency check

```textGit
Python
Node
Browser
PowerShell
```

حسب الأدوات المطلوبة.

---

# 41. PHASE 40 — First Run Experience

عند أول تشغيل:

```text
Welcome
↓
Hardware scan
↓
Storage selection
↓
Model selection
↓
Browser setup
↓
Speech setup
↓
Git setup
↓
GitHub optional
↓
Computer control setup
↓
Benchmark
↓
Ready
```

---

# 42. PHASE 41 — Final Demo Scenarios

هذه ليست Demos بسيطة؛ هي **Acceptance Scenarios**.

---

## Scenario A — Build project

> "ابنِ لي المشروع كاملًا."

NEXUS:

```text
Understand
Research
Architecture
Workspace
Coding
Testing
Debug
Security
Git
Verify
```

---

## Scenario B — Word

> "اعمل التقرير."

NEXUS:

```text
Research
Word
Formatting
Sources
Verify
```

---

## Scenario C — Browser

> "ابحث عن أفضل repositories."

NEXUS:

```text
GitHub
Web
ranking
analysis
report
```

---

## Scenario D — War Thunder

> "حلل مواصفات الجهاز واضبط الإعدادات."

NEXUS:

```text
Hardware
Game window
UI
Visual observation
Settings
Apply
Observe
Report
```

والـComputer Use هنا يبقى في نطاق الإعداد والمراقبة والتشخيص، وليس لعب اللعبة بدل المستخدم أو تجاوز أنظمة الحماية.

---

## Scenario E — Offline

```text
Internet off
→ local work continues
→ network task waits
→ internet returns
→ resume
```

---

## Scenario F — Power loss

```text
task
→ checkpoint
→ restart
→ recover
→ inspect
→ resume
```

---

# 43. PHASE 42 — Repository Integration Order

هذا هو الترتيب الذي يجب على الوكيل اتباعه.

```text
1. NEXUS Core
2. SQLite/Event system
3. llama.cpp
4. Model Manager
5. Agent abstraction
6. Cline/ECC patterns
7. LangGraph/Prime patterns
8. Tool Registry
9. MCP
10. Filesystem
11. Terminal
12. Windows runtime
13. Windows Harness
14. UIA/pywinauto
15. Window Manager
16. Browser
17. Playwright
18. Browser Use
19. Browser Harness
20. Memory
21. Mem0
22. Qdrant
23. Code intelligence
24. Tree-sitter
25. Aider concepts
26. Coding agents
27. Git/GitHub
28. Research
29. Documents
30. Speech
31. Vision
32. Verification
33. Recovery
34. Plugins
35. Learning
36. Desktop UI polish
37. Remote
38. Full-system hardening
```

---

# 44. قاعدة مهمة جدًا للـAgent في كل مرحلة

كل مرحلة صغيرة يجب أن تنتهي بهذه الدورة:

```text
IMPLEMENT
↓
TEST
↓
VERIFY
↓
COMMIT
↓
DOCUMENT
↓
NEXT
```

---

# 45. Repository Staging Directory

قبل دمج أي Repository:

```text
vendor-staging/
└── PHASE-XX/
    └── repository-name/
```

مثال:

```text
vendor-staging/
└── phase-08/
    └── windows-harness/
```

---

# 46. Repository Intake Record

أنشئ لكل Repo:

```text
repo-intake.json
```

محتواه المفاهيمي:

```json
{
  "name": "…",
  "url": "…",
  "version": "…",
  "commit": "…",
  "license": "…",
  "integration_mode": "ADAPT",
  "purpose": "…",
  "files_used": [],
  "files_rejected": [],
  "dependencies": [],
  "security_review": "…"
}
```

---

# 47. لا تنسخ المستودع كاملًا إلى NEXUS

القاعدة:

```text
Clone
≠
Copy everything
```

الوكيل يجب أن يعرف بالضبط:

```text
what
why
where
how
license
dependencies
```

---

# 48. Repository Pinning

بعد الدمج:

```textRepo id="5x1fnu"
Commit
Tag/version
Hash
```

يثبت.

وكل upgrade مستقبلي يعتبر مهمة منفصلة.

---

# 49. Repository Update Process

```text
detect update
↓
read changelog
↓
compatibility test
↓
security test
↓
integration test
↓
upgrade
```

---

# 50. Dependency Isolation

يفضل عزل dependencies الثقيلة.

مثال:

```textbrowser runtime id="3y9t0d"
model runtime
document engine
```

بحيث لا تسبب conflict مع Core.

---

# 51. Adapter Layer

أمثلة:

```text
adapters/
├── llama_cpp
├── cline
├── langgraph
├── browser_use
├── playwright
├── windows_harness
├── pywinauto
├── mem0
├── qdrant
├── docling
└── speech
```

---

# 52. Fallback Layer

كل Adapter يجب أن يستطيع:

```textavailable
unavailable
error
fallback
```

مثال:

```textBrowser Use unavailable
→ Playwright direct
→ Computer Use
```

---

# 53. Agent Fallback

مثال:

```textCoder Agent unavailable
→ alternative coding agent
→ Master direct
```

---

# 54. Model Fallback

```textModel A unavailable
→ Model B
→ smaller Model
```

---

# 55. Tool Fallback

```textAPI unavailable
→ Browser
→ UI
→ Vision
```

---

# 56. Verification Fallback

إذا طريقة تحقق غير متاحة:

```textMethod A unavailable id="47k05j"
→ Method B
→ Method C
```

ولا تعلن success بدون تحقق مناسب.

---

# 57. Context Management

كل model call:

```textSystem
+
Role
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
Current observation
```

ولا ترسل كل history دائمًا.

---

# 58. Context Compaction

عندما يطول Task:

```textold turns
→ summary
```

لكن احتفظ:

```textcritical decisions
errors
constraints
current state
```

---

# 59. Conversation Continuity

إذا قلت:

> "كمل."

NEXUS يجب أن يحدد:

```textwhich conversation
which task
which workspace
which checkpoint
which state
```

ثم يكمل.

---

# 60. Task Resume

لا يفترض الحالة.

يفحص:

```textfilesystem
processes
git
browser
checkpoint
memory
```

ثم يقرر.

---

# 61. Reconciliation Engine

هذه خدمة مستقلة:

```textSaved State id="u5v9yh"
+
Actual Environment
↓
Reconciliation
↓
Current World State
```

---

# 62. World Model

يحفظ:

```textapps
windows
files
processes
browser
task
git
```

---

# 63. Computer Observation Loop

```textAction
↓
Observation
↓
World Model update
↓
Verify
```

---

# 64. Browser Observation Loop

```textNavigate
↓
DOM/screenshot
↓
state
↓
decision
```

---

# 65. Application Observation Loop

```textOpen
↓
UI tree/screen
↓
action
↓
result
```

---

# 66. Resource-aware Agent Scheduling

Scheduler يقرر:

```textagent priority
model
parallelism
memory budget
```

---

# 67. Priority System

مثال:

```textUser command
>
Recovery
>
Current task
>
Verification
>
Background learning
```

---

# 68. Background Learning Priority

لا يسمح لـlearning أن يسرق الموارد من مهمة المستخدم.

---

# 69. Remote Priority

أمر من المستخدم على الهاتف:

> "وقف المهمة."

يجب أن تكون أولوية أعلى من background workers.

---

# 70. Plugin Security

كل Plugin يعلن permissions.

---

# 71. MCP Security

كل MCP tool يمر بـNEXUS gate.

---

# 72. Skill Security

Skill generated لا تحصل تلقائيًا على all tools.

---

# 73. Agent Security

Agent لا يرث صلاحيات غير مطلوبة.

---

# 74. Full Autonomy L4

عندما يختار المستخدم المستوى 4:

```text
No repeated confirmations
```

لكن:

```text
Task scope still applies
```

---

# 75. Clarification Rule

إذا نقصت معلومة جوهرية:

```text
ask before long execution
```

إذا يمكن استنتاجها:

```text
do not ask
```

إذا يمكن البحث عنها:

```text
research
```

---

# 76. Research-before-ask

مثال:

```text
User didn't specify package version
↓
Check project
↓
Check compatible version
↓
Proceed
```

ولا تسأل المستخدم بلا داعٍ.

---

# 77. External AI-before-user

إذا النموذج المحلي لا يفهم:

```text
local model insufficient
↓
search
↓
consult external AI if allowed
↓
continue
```

لكن إذا ما زالت المعلومة **جوهرية ومفقودة**، اسأل المستخدم عند نقطة مبكرة مناسبة.

---

# 78. Long Task Policy

عند إنشاء المهمة:

```text
time policy
```

تحدد:

```text
deadline
or
until goal completion
```

---

# 79. Completion Contract

لا يوجد:

```text"probably done"
```

بل:

```textsuccess criteria met
+
verification evidence
```

---

# 80. Final Report Generator

عند نهاية المهمة:

```textGoal
Completed work
Files changed
Apps used
Tools used
Tests
Verification
Git
Warnings
```

---

# 81. User-visible Activity

يظهر:

```text
Master
Planner
Research
Coder
Tester
Reviewer
```

مع الخطوة التنفيذية الحالية.

---

# 82. Internal vs External Reasoning

الواجهة تعرض:

```textdecision summary
action
tool
result
evidence
```

ولا تعرض private chain-of-thought الخام.

---

# 83. NEXUS Learning Log

بالإضافة إلى task history:

```textlessons learned
successful patterns
failed approaches
skills
```

---

# 84. Task History UI

زر:

> View history

يعرض:

```textPrompt
Plan
Activity
Errors
Repairs
Checkpoints
Result
```

---

# 85. Scoped Rollback

Rollback المشروع:

```textcode
files
git
```

ولا يمس:

```textmemory
learning
conversation
```

إلا بطلب منفصل.

---

# 86. Model Benchmark Command

يجب أن يكون هناك أمر:

```text
benchmark models
```

يعطي:

```textmodel
speed
RAM
VRAM
context
stability
recommendation
```

---

# 87. Hardware Analysis Command

```text
analyze my computer
```

يعطي:

```textHardware
software
performance
limitations
recommended models
```

---

# 88. Computer Diagnostics

```text
diagnose computer control
```

يفحص:

```textUIA
input
windows
screen capture
browser
permissions
```

---

# 89. Browser Diagnostics

```text
diagnose browser
```

يفحص:

```textChrome
Edge
Playwright
CDP
sessions
downloads
```

---

# 90. Model Diagnostics

```text
diagnose models
```

يفحص:

```textfiles
runtime
RAM
VRAM
load
health
```

---

# 91. NEXUS Doctor

يجمع:

```textCore
Models
Computer
Browser
Memory
Tools
Git
Remote
```

---

# 92. Final Repository Arsenal

## Production candidates

```text
llama.cpp
Playwright
Browser Use
Browser Harness
Windows Harness
pywinauto
MCP SDK
Mem0
Qdrant
Tree-sitter
Docling
sherpa-onnx
```

## Architecture/component candidates

```text
Cline
ECC
LangGraph
Prime Agent
Deep Agents
OpenHands
OpenCode
Aider
Microsoft Agent Framework
Letta Code
```

## Research/reference

```text
UI-TARS
OpenCUA
Agent-S
CUA reference implementations
win-computer-use
```

## Testing

```text
OSWorld-V2
BrowserGym
SWE-bench
OpenAI Evals
```

## Security/quality

```text
Trivy
Semgrep
Pyright
selected guardrail tooling
```

## Remote/reference

```text
RustDesk
WebRTC tooling
Socket.IO/realtime tooling
```

---

# 93. Final Integration Matrix

| النظام            | Repository      | القرار              | متى يدخل؟      |
| ----------------- | --------------- | ------------------- | -------------- |
| Local inference   | llama.cpp       | USE                 | مبكرًا         |
| Agent patterns    | ECC             | ADAPT               | Agent phase    |
| Agent SDK         | Cline           | ADAPT/REFERENCE     | Agent phase    |
| Orchestration     | LangGraph       | USE/ADAPT           | State phase    |
| Long horizon      | Prime           | REFERENCE/ADAPT     | Recovery       |
| Browser execution | Playwright      | USE                 | Browser phase  |
| Browser agent     | Browser Use     | USE/ADAPT           | Browser phase  |
| Browser harness   | Browser Harness | ADAPT               | Browser phase  |
| Windows           | Windows Harness | ADAPT               | Computer phase |
| Windows UI        | pywinauto       | USE                 | Computer phase |
| Memory            | Mem0            | USE/ADAPT           | Memory phase   |
| Retrieval         | Qdrant          | USE                 | Memory phase   |
| Parsing           | Tree-sitter     | USE                 | Coding phase   |
| Code mapping      | Aider           | REFERENCE/EXTRACT   | Coding phase   |
| Coding            | OpenHands       | ADAPT/REFERENCE     | Coding phase   |
| Coding            | OpenCode        | REFERENCE           | Coding phase   |
| Docs              | Docling         | USE                 | Document phase |
| Speech            | sherpa-onnx     | USE after benchmark | Speech phase   |
| Protocol          | MCP             | USE                 | Tool phase     |
| GUI research      | UI-TARS         | REFERENCE           | Vision phase   |
| Computer eval     | OSWorld         | TEST                | Evaluation     |
| Browser eval      | BrowserGym      | TEST                | Evaluation     |
| Security          | Trivy           | USE                 | Verification   |
| Python static     | Pyright         | USE                 | Verification   |
| Optimization      | DSPy            | REFERENCE/POSSIBLE  | Learning       |

---

# 94. Final Build Order — التنفيذ الإجباري

الوكيل لا يبدأ بواجهة جميلة.

الترتيب:

```text
1. GitHub repository
2. Workspace
3. Core
4. Events
5. Task state
6. Persistence
7. Scope
8. Permissions
9. Hardware
10. Resource manager
11. Model abstraction
12. llama.cpp
13. Model registry
14. Model router
15. Master Agent
16. Agent runtime
17. Tool registry
18. MCP
19. Files
20. Terminal
21. Windows runtime
22. UIA
23. Computer control
24. Window manager
25. Browser runtime
26. Playwright
27. Browser Use
28. Browser Harness
29. Memory
30. Qdrant
31. Mem0
32. Code intelligence
33. Tree-sitter
34. Coding agents
35. Git
36. GitHub
37. Research
38. Documents
39. Speech
40. Vision
41. Verification
42. Recovery
43. Heartbeat
44. Multi-agent
45. Learning
46. Plugins
47. Skills
48. Desktop UI
49. Tray/startup
50. Remote protocol
51. Remote web
52. Remote file transfer
53. Security hardening
54. Evaluation
55. Fault injection
56. Packaging
57. Production validation
```

---

# 95. Definition of Done لكل مرحلة

كل مرحلة لا تُعتبر منتهية إلا عند تحقق:

```text
Implemented
+
Integrated
+
Tested
+
Verified
+
Documented
+
Committed
```

---

# 96. Definition of Done للـRepository

لكل Repository:

```text
Cloned
License checked
Security reviewed
Version pinned
Purpose documented
Adapter created where required
Integrated or rejected explicitly
Tests passed
Commit created
```

---

# 97. Definition of Done للنظام

كل subsystem يجب أن يملك:

```textimplementation
test
health check
failure path
logging
verification
documentation
```

---

# 98. Definition of Done للمنتج النهائي

NEXUS لا يعتبر نهائيًا حتى يستطيع:

```text
Understand natural Arabic/English instructions
+
Create long-running tasks
+
Operate within scoped workspaces
+
Use local models
+
Route models intelligently
+
Use multi-agent orchestration
+
Use Windows apps
+
Use mouse/keyboard/screen
+
Use browser
+
Use terminal
+
Manage files
+
Build software
+
Understand large repositories
+
Use Git/GitHub
+
Research web
+
Read/write documents
+
Use speech
+
Use vision
+
Verify results
+
Repair failures
+
Recover after restart
+
Continue after internet loss
+
Persist memory
+
Learn reusable skills
+
Operate plugins/MCP
+
Run in background
+
Show activity
+
Support remote web control
```

---

# 99. Final Acceptance Scenario

المستخدم يعطي:

> "ابني لي مشروع X على القرص M. ابحث عن أفضل الطرق والمشاريع الموجودة، صمم architecture، نفذ المشروع، اختبره، أصلح الأخطاء، راجع الأمان، جهز GitHub، وبعدها اشرح لي النتيجة."

المطلوب:

```text
NEXUS
↓
Understand
↓
Check clarification
↓
Create scope
↓
Select workspace
↓
Plan
↓
Research
↓
GitHub
↓
Architecture
↓
Delegate
↓
Code
↓
Run
↓
Observe
↓
Test
↓
Repair
↓
Security
↓
Review
↓
Git
↓
GitHub
↓
Verify
↓
Checkpoint
↓
Memory
↓
Learning
↓
Final result
```

---

# 100. Final Recovery Scenario

المهمة تعمل منذ ساعتين.

يحدث:

```text
Power interruption
```

بعد Windows boot:

```text
NEXUS starts
↓
Finds interrupted task
↓
Loads state
↓
Checks filesystem
↓
Checks Git
↓
Checks processes
↓
Checks browser
↓
Reconciles
↓
Shows Resume
↓
Continue
```

---

# 101. Final Offline Scenario

```text
Task running
↓
Internet disappears
↓
Local tools continue
↓
Network dependency reached
↓
WAITING_NETWORK
↓
Internet returns
↓
Dependency resumes
↓
Task continues
```

---

# 102. Final Human + AI Scenario

```text
User:
War Thunder

NEXUS:
Chrome + research

Monitor 1:
User

Monitor 2:
NEXUS

NEXUS:
computer control active

User:
continues his own work
```

والـWindow Manager يمنع التخبط بين الـuser-owned والـNEXUS-owned windows.

---

# 103. Final Learning Scenario

```text
Repeated task
↓
Experience
↓
Pattern detected
↓
Skill candidate
↓
Test
↓
Verify
↓
Install
↓
Future reuse
```

---

# 104. Final Model Scenario

```text
Task
↓
Resource scan
↓
Model candidates
↓
Capability matching
↓
Benchmark profile
↓
Choose
↓
Load
↓
Execute
↓
Unload/keep warm
```

---

# 105. Final Repository Rule

إذا وجد الوكيل Repository جديدًا أثناء البناء:

لا يدخله مباشرة.

بل:

```text
Discover
→ Intake
→ License
→ Security
→ Compatibility
→ Architecture
→ Decision
```

ثم:

```text
USE
ADAPT
EXTRACT
REFERENCE
TEST
REJECT
```

---

# 106. Final Engineering Rule

إذا كان هناك Repository يحل المشكلة بشكل ممتاز:

> لا تعِد اختراع الحل.

إذا كان Repository يجبر NEXUS على Architecture سيئة:

> لا تستخدمه حتى لو كان مشهورًا.

إذا كان Repository ممتازًا لكن غير مناسب لـWindows:

> استخدمه كمرجع فقط.

إذا كان Repository تجريبيًا مثل Windows Harness:

> ضع abstraction فوقه حتى يمكن استبداله لاحقًا. ([github.com](https://github.com/browser-use/windows-harness?utm_source=chatgpt.com))

---

# 107. Final Ownership Map

```text
                   NEXUS
                      │
         ┌────────────┴────────────┐
         │                         │
     OUR CORE                 EXTERNAL ENGINES
         │                         │
         ▼                         ▼
Task / Scope / Memory        llama.cpp
Orchestrator                 Playwright
Permissions                  Browser Use
Resource Manager             Windows Harness
Model Manager                pywinauto
Verification                 Mem0
Recovery                     Qdrant
Plugins                      Tree-sitter
Remote                       Docling
UI                           sherpa-onnx
         │                    MCP
         │
         ▼
      ADAPTERS
         │
         ▼
   EXTERNAL PROJECTS
```

---

# 108. Final Strategic Rule

لا تجعل NEXUS:

```text
ECC clone
Cline clone
OpenHands clone
Browser Use clone
```

بل:

```text
NEXUS
+
best capabilities
+
best infrastructure
+
our orchestration
+
our memory
+
our recovery
+
our Windows layer
```

---

# 109. النتيجة النهائية

بعد تنفيذ كل المراحل، يجب أن يصبح الناتج:

```text
NEXUS
│
├── Local AI
├── Master Agent
├── Multi-Agent
├── Long-running Tasks
├── Memory
├── Learning
├── Windows Computer Use
├── Browser
├── Files
├── Terminal
├── Applications
├── Documents
├── Research
├── Git
├── GitHub
├── Verification
├── Recovery
├── Checkpoints
├── Plugins
├── Skills
├── MCP
├── Resource Management
├── Desktop UI
└── Remote Web
```

والدورة الأساسية:

```text
USER
 ↓
PROMPT
 ↓
UNDERSTAND
 ↓
SCOPE
 ↓
PLAN
 ↓
MASTER AGENT
 ↓
SPECIALISTS
 ↓
TOOLS
 ↓
COMPUTER
 ↓
OBSERVE
 ↓
VERIFY
 ↓
REPAIR
 ↓
CHECKPOINT
 ↓
MEMORY
 ↓
LEARN
 ↓
CONTINUE
 ↓
FINAL VERIFY
 ↓
RESULT
```

هذه هي **خطة البناء النهائية** التي تُستخدم بعد مواصفة NEXUS الرئيسية، بحيث يستطيع وكيل التنفيذ البدء من Repository + Workspace على جهازك، ثم السير مرحلة مرحلة، وكل مرحلة صغيرة لها Repository/مصدرها، ومكان دمجها، واختبارها، ومعيار اكتمالها. وهي متعمدة على أن يكون NEXUS هو النظام المالك للـCore، بينما المشاريع المفتوحة تصبح محركات أو Adapters قابلة للاستبدال. ومتطلباتك الأصلية تظل المرجع الوظيفي الأساسي: إدارة الكمبيوتر، المهام الطويلة، المشاريع، المتصفح، التطبيقات، الذاكرة، الانقطاع، النسخ الاحتياطية، Git/GitHub، والعمل عن بعد.
