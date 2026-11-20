# Contributing to NEXUS · المشاركة في NEXUS

<div dir="rtl">

## القواعد الحاكمة (غير قابلة للتفاوض)

1. **الوثيقتان أولاً**: اقرأ [المواصفة المرجعية](docs/reference/NEXUS-Master-Technical-Specification-v1.0.md) (ماذا نبني) ثم [خطة البناء](docs/reference/NEXUS-Final-Build-Plan-v1.0.md) (كيف وبأي ترتيب). أي كود يخالفهما = Bug.
2. **دورة كل مرحلة صغيرة**: `IMPLEMENT → TEST → VERIFY → COMMIT → DOCUMENT → NEXT` — لا استثناءات.
3. **قاعدة الـAdapter**: `NEXUS Interface → Adapter → External Project` — ممنوع أن يعتمد NEXUS Core مباشرة على internal APIs خارجية.
4. **الملكية**: المكونات الـ24 المملوكة لـNEXUS *(Plan §0.5)* لا تُفوَّض لأي مستودع خارجي.
5. **دورة intake لأي مستودع جديد — حرفيًا كما في الخطة §0.2 (12 خطوة)**: `DISCOVER → CLONE TO STAGING → LICENSE AUDIT → SECURITY REVIEW → ARCHITECTURE REVIEW → COMPATIBILITY REVIEW → SELECT INTEGRATION MODE → ADAPTER / EXTRACT / USE → INTEGRATE INTO NEXUS → TEST → PIN VERSION/COMMIT → DOCUMENT`.

## سير العمل

- فرع `develop` هو فرع التطوير. `main` محمي — لا دفع مباشر إليه.
- لكل feature: `feature/<اسم>-<رقم-الـissue>` من `develop`.
- اجعل الـPRs صغيرة وقابلة للمراجعة. اجعل الـcommits ذرية برسائل Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`...).
- CI يجب أن ينجح قبل الدمج — ولا يُدمج في `main` دون نجاح التحقق الأساسي.
- اللغة: الكود والمعرفات بالإنجليزية؛ التوثيق ثنائي اللغة (عربي/إنجليزي) كما في الوثيقتين.

</div>

## Governing rules (non-negotiable)

1. **Documents first**: read the [Master Specification](docs/reference/NEXUS-Master-Technical-Specification-v1.0.md) (*what*) then the [Final Build Plan](docs/reference/NEXUS-Final-Build-Plan-v1.0.md) (*how & order*). Any conflicting code is a bug.
2. **Per-step cycle**: `IMPLEMENT → TEST → VERIFY → COMMIT → DOCUMENT → NEXT` — no exceptions.
3. **Adapter rule**: `NEXUS Interface → Adapter → External Project` — NEXUS Core never depends on foreign internal APIs.
4. **Ownership**: the 24 NEXUS-owned components *(Plan §0.5)* are never fully delegated to an external repository.
5. **Repo intake cycle — verbatim per Plan §0.2 (12 steps)**: `DISCOVER → CLONE TO STAGING → LICENSE AUDIT → SECURITY REVIEW → ARCHITECTURE REVIEW → COMPATIBILITY REVIEW → SELECT INTEGRATION MODE → ADAPTER / EXTRACT / USE → INTEGRATE INTO NEXUS → TEST → PIN VERSION/COMMIT → DOCUMENT`.

## Workflow

- `develop` is the development branch; `main` is protected — no direct pushes.
- Feature branches: `feature/<name>-<issue>` off `develop`.
- Keep PRs small and reviewable; use atomic Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`...).
- CI must pass before merge — nothing lands on `main` without the basic checks.
- Language: code & identifiers in English; documentation bilingual (AR/EN), matching the canonical documents.

---

## دورة الـ Sub-Phase الإلزامية (18 خطوة) · The Mandatory Sub-Phase Cycle

> **مثبّتة بأمر المشغّل من PHASE 6 فصاعدًا** — كل مرحلة رئيسية تنقسم
> إلى Sub-Phases، وكل Sub-Phase تجتاز هذه الدورة كاملة قبل إعلان
> اكتمالها. الدورة تُوسّع قاعدة §0.2 (12 خطوة للمستودعات) إلى دورة
> هندسية كاملة تشمل الاختبارات الحقيقية والاسترداد.

```text
 1. Define requirement      — تعريف متطلب الـ Sub-Phase من الخطة/المواصفة
 2. Discover repositories   — اكتشاف المستودعات الناضجة المرشحة
 3. Audit repositories      — تدقيق التراخيص والأمان والمعمارية
 4. Select integration      — اختيار استراتيجية الدمج (MODE A–F + §0.5)
 5. Clone required repos    — السحب إلى vendor-staging بتثبيت إصدار
 6. Inspect source          — فحص المصدر فعليًا (لا افتراضات)
 7. License verification    — التحقق النهائي من الترخيص قبل أي دمج
 8. Security review         — مراجعة أمنية لما سيُدمج فقط
 9. Extract components      — استخراج الأنماط/المكونات المطلوبة
10. Integrate into NEXUS    — الدمج خلف واجهات NEXUS (§0.4)
11. Write NEXUS adapters    — كتابة المحولات المملوكة لـNEXUS
12. Unit tests              — اختبارات وحدة لكل مكون جديد
13. Integration tests       — اختبارات تكامل مع المكونات القائمة
14. Real Windows tests      — اختبارات على جهاز ويندوز الحقيقي
15. Failure/recovery tests  — اختبارات الفشل والاسترداد
16. CI                      — البوابات الخضراء على GitHub Actions
17. Documentation           — التوثيق (تقرير المرحلة + سجل المستودعات)
18. Git commit + checkpoint — الالتزام + نقطة تفتيش + دفع مزدوج
```

وبعدها فقط:

```text
SUB-PHASE COMPLETE → PHASE COMPLETE → SYSTEM INTEGRATION TEST → NEXT PHASE
```

**English summary:** every sub-phase from Phase 6 onward runs the full
18-step cycle above (requirement → discovery → audit → strategy →
clone → inspect → license → security → extract → integrate → adapt →
unit → integration → real-Windows → failure/recovery → CI → docs →
commit+checkpoint). Steps 14–15 run on the operator's Windows machine
(via the bridge or locally); steps 5–6 happen in `vendor-staging/`
(gitignored, pins recorded in `docs/REPOSITORY-INTEGRATION.md`).
