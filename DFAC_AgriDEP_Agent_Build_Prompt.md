# Build Prompt: DFAC AgriDEP (Agricultural Data Ecosystem Platform)

> Attach `DFAC_Agricultural_Ecosystem_Platform_Framework.docx` to the agent together with this prompt. The framework document is the functional source of truth. This prompt tells you how to build it. If the two conflict, follow this prompt on technology and the framework on business logic, and flag the conflict to me.

---

## 1. Your role and mission

You are a senior full-stack engineer and technical lead. Build **DFAC AgriDEP**, a multi-stakeholder agricultural data platform for Doctor Fish Agricultural Consult (DFAC), a Nigerian agri-consultancy focused on catfish and other aquaculture, plus crops, snails and poultry.

The platform captures data once, at the point of activity, and routes it automatically to every actor who needs it. The actors are farmers, field officers, trainers, lenders, buyers/off-takers and DFAC management. It is **decision-workflow driven**: success means the system answers questions on its own, such as which farm needs a visit this week, which loan is drifting into risk, and which farmers can meet a buyer's demand. Storing data and drawing dashboards is not enough.

The deployment context is rural Niger Delta, Nigeria. Connectivity is poor, many farmers only have feature phones, and the data is personal and financial.

## 2. Non-negotiable constraints

1. **One source of truth.** Farmer, Farm and Buyer are the three identity anchors. No module duplicates farmer or buyer details; everything references these by ID.
2. **Offline-first field capture.** Field officers must be able to register farmers, log production, run inspections and record visits with no signal, then sync automatically. This is a hard requirement.
3. **RBAC enforced at the API/service layer**, never only in the UI. Use object-level and row-level scoping, not just role checks. See section 6.
4. **Privacy.** Align with the Nigeria Data Protection Act 2023. Capture per-stakeholder consent at registration, encrypt data in transit and at rest, apply field-level encryption to the NIN and phone numbers, and keep an immutable audit log of all access to and changes of financial data.
5. **Phased delivery.** Each phase must be demoable and valuable on its own. Do not build everything at once.
6. **API-first, versioned and documented** from day one (`/api/v1/`, OpenAPI schema). Future lender, ERP and weather integrations must plug in without re-architecture.
7. **Stateless application tier** so it scales from hundreds to several thousand farmers across states without a redesign.

## 3. Tech stack (use this unless you have a strong, stated reason to deviate)

| Concern | Choice |
|---|---|
| Backend | **Python 3.12 + Django 5 + Django REST Framework**, with drf-spectacular for OpenAPI |
| Database | **PostgreSQL 16 + PostGIS** (GeoDjango) |
| Background jobs / rules engine | **Celery + Celery Beat + Redis** |
| Auth | Django auth with JWT for mobile (SimpleJWT), session auth for the web portals. Phone-number login with OTP via SMS for farmers. |
| Permissions | Custom permission classes plus queryset scoping (a `ScopedQuerySetMixin`), and `django-guardian` or an equivalent for object-level rules |
| Audit | `django-auditlog` or `django-simple-history`, plus an explicit `AuditEvent` for reads of sensitive data |
| Web portals | Server-rendered Django templates with HTMX and Alpine.js, styled with Tailwind. Light and fast on low bandwidth. Mobile-responsive. |
| Field mobile app | **Flutter (Android-first)** with local SQLite (Drift), an outbox queue and a delta-sync API. Build this after the API is stable (milestone M5). Until then, provide an ODK/Kobo ingestion endpoint so DFAC can start collecting data in Phase 1. |
| SMS / USSD | **Africa's Talking** (SMS, USSD, OTP), behind an adapter interface with a console/mock provider for dev |
| Files | S3-compatible object storage (django-storages); MinIO locally |
| Reports | openpyxl for Excel, WeasyPrint for PDF, scheduled via Celery |
| Analytics | Built-in role-scoped dashboards. Optionally add Metabase for internal DFAC staff only, never for external roles. |
| Infra | Docker + docker-compose for local dev. Production: containers on AWS (af-south-1) or an equivalent regional cloud, with managed Postgres. GitHub Actions CI. |
| Quality | pytest + pytest-django + factory_boy, ruff, mypy (lenient), pre-commit, 80%+ coverage on business rules and permissions |

## 4. Architecture

Four layers, with each layer replaceable on its own:

1. **Data capture:** Flutter offline app, USSD/SMS gateway, web forms (trainers, buyers, lenders), ODK/Kobo ingestion.
2. **Central data:** PostgreSQL/PostGIS, object storage.
3. **Application/API:** Django services. Put business logic in `services.py` and `rules/` modules, **not** in views or serializers. Views stay thin.
4. **Presentation:** role-scoped portals, PDF/Excel exports, SMS/USSD prompts and alerts.

Suggested repo layout (a modular monolith, one Django app per bounded context):

```
agridep/
  config/                 # settings (base/dev/prod), celery, urls
  apps/
    accounts/             # users, roles, OTP, consent, org memberships
    registry/             # Farmer, Farm, Buyer, Lender, Trainer, Supplier, cohorts
    production/           # cycles, logs, inspections, harvest forecasts, Produce Batch
    training/             # programmes, sessions, attendance, assessments, certificates
    finance/              # applications, loans, tranches, repayments, risk
    inputs/               # supplier directory, input orders, delivery confirmation
    market/               # prices, demand, offers, matches, off-take transactions
    fieldops/             # visits, inspections, incidents, visit-priority list
    alerts/               # rule definitions, alert instances, notification dispatch
    reporting/            # indicators, dashboards, exports, scheduled reports
    sync/                 # offline sync protocol, ODK/Kobo ingest
    audit/                # audit events
    common/               # base models, permissions, validators, utils
  mobile/                 # Flutter app (from M5)
  docs/                   # architecture, ADRs, data dictionary, API guide, runbook
  docker/  .github/  Makefile  README.md
```

## 5. Data model (build on this; extend where needed)

Use UUID primary keys, plus a human-readable code (e.g. `DFAC-FRM-000123`). Every table has `created_at`, `updated_at`, `created_by` and `is_deleted` (soft delete). Each synced record also has `client_id` and `client_updated_at` for offline idempotency. Use PostGIS `PointField` for locations.

**Identity anchors:** `Farmer`, `Farm`, `Buyer`.
**Other actors:** `Lender`, `Trainer`, `Supplier`, `FieldOfficer` (a profile on `User`), `Cohort`/`Area` (for officer assignment scoping).
**Core entities from the framework:** `Farmer`, `Farm`, `ProduceBatch`, `TrainingRecord`, `LoanRecord`, `OfftakeTransaction`, `InputOrder`, `FarmVisit`.
**Supporting entities you must add:**
- `ProductionCycle`, `ProductionLog` (stocking, growth, water quality, disease, inspections), `HarvestForecast`, `HarvestRecord`
- `TrainingProgramme`, `TrainingSession`, `Attendance`, `Assessment`, `Certificate` (with expiry)
- `LoanApplication`, `LoanTranche`, `RepaymentSchedule`, `Repayment`, `RiskFlag`, `CreditScoreSnapshot`
- `BuyerDemand` (produce type, volume, grade, window, location), `Match` (status: proposed → confirmed → fulfilled/declined), `CommodityPrice`
- `Alert`, `AlertRule`, `NotificationLog`, `VisitAssignment`
- `ConsentRecord` (farmer, stakeholder category, scope, timestamp, channel)
- `AuditEvent`

Enterprise types are configurable (catfish, tilapia, snail, crop, poultry). Seed them as data, not as hard-coded enums.

Deliver an ERD (Mermaid in `docs/`) and a data dictionary.

## 6. Roles and permissions (enforce in the service/API layer, with tests)

| Role | Can see | Must NOT see |
|---|---|---|
| Farmer | Own profile, farm, training, loan status, matched buyer offers | Other farmers' data; buyer/lender internals |
| Field Officer | Full records of assigned farmers (by cohort/area); visit tools | Farmers outside their assignment; other officers' private notes |
| Trainer | Assigned trainees' attendance and assessments | Any loan, financial or off-take data |
| Lender | Loan/repayment data for their own financed farmers, plus relevant production data | Other lenders' portfolios; unrelated farmer data |
| Buyer | **Aggregated** produce availability and matched-farmer readiness | Farmer identity until a match is confirmed; any loan/financial data |
| DFAC Admin/Management | Everything, with activity logging | Nothing is hidden, but every access is audited |

Requirements:
- Implement a central `scope_queryset(user, model)` policy so list endpoints can never leak rows.
- **Write a permissions test matrix**: for each role × resource × action, assert allow or deny. Include explicit tests such as "buyer cannot retrieve loan endpoints", "lender A cannot fetch lender B's loan by ID (404, not 403)", and "buyer sees masked farmer fields before match confirmation".
- Mask or redact fields in serializers by role (field-level visibility).

## 7. Decision workflows (the core product value)

Implement a rules engine as code. Each rule is a function with a clear trigger and condition that emits `Alert` and `VisitAssignment` objects and dispatches notifications. Make thresholds **configurable in the database/admin**, not hard-coded. Run rules on write (signals/services) and on a nightly Celery Beat schedule.

| Trigger | Condition | Action | Recipients |
|---|---|---|---|
| Production update logged | Projected harvest within 14 days | Flag farmer harvest-ready; run buyer matching | Field officer, matched buyer(s) |
| Repayment due date | No repayment 7 days past due | Raise loan risk flag; schedule farm visit | Lender, field officer, DFAC finance |
| Production trend logged | Actual yield materially below projection | Early-warning risk flag on linked loan | Lender, field officer |
| Buyer demand registered | Matching farmer volume in region/window | Notify buyer and farmer; propose match | Buyer, farmer (via officer/SMS) |
| Certification issued | Loan application by certified farmer | Apply credit-score adjustment | Lender |
| Visit overdue | No visit in a configurable interval (default 60 days) | Add farm to visit-priority list | Field officer, DFAC coordinator |
| Certification nearing expiry | Within a configurable window | Notify trainee and trainer | Farmer, trainer |
| Input order tranche gate | Previous input delivery not confirmed | Block release of the next tranche | Lender, DFAC finance |

Also implement:
- **Buyer-matching algorithm**: match on produce type, volume, region/radius (PostGIS), harvest window and grade. Return ranked farmer groups and aggregate them to a volume. Include the "buyer needs X tonnes by month Y" example from the framework as a test.
- **Loan expected-value and risk model** (v1, rule-based and transparent): expected harvest value vs loan amount and repayment schedule, tracking actual vs projected pace. Use the framework's example (₦200,000 loan against ₦850,000 expected harvest) as a test fixture.
- **Prioritised visit list** per officer, ranked by risk flags, overdue visits, and incidents.

## 8. Phased build plan

Work milestone by milestone. At the end of each: all tests green, migrations clean, docs updated, a short demo script in `docs/demo/`, and a commit/PR summary.

- **M0 Foundations:** repo, Docker, CI, settings split, base models, accounts/roles, audit, consent, seed data, OpenAPI.
- **M1 Registry + Production (Phase 1):** Farmer/Farm registry with duplicate-farmer detection (phone, NIN, fuzzy name + location), GPS, enterprise types; production cycles and logs; harvest forecasts; ODK/Kobo ingestion endpoint; field-officer web forms.
- **M2 Training + Dashboard (Phase 1):** programmes, sessions, attendance, assessments, certificates; import of existing attendance sheets (CSV/Excel); basic DFAC dashboard (farmer counts, map of farms, production status).
- **M3 Finance + Market (Phase 2):** loans, tranches, repayments, risk flags; buyer demand, matching, off-take transactions; harvest-ready alerts; full RBAC with portals for lender and buyer.
- **M4 Field Ops (Phase 2):** visits, inspections, geo-tagged photos, incidents, auto-generated visit-priority lists.
- **M5 Flutter offline app:** offline registration, production logs, visits and photos; outbox queue; delta sync with conflict handling (server-wins on financial fields, last-write-wins with audit on field data); background sync; low-end Android performance.
- **M6 SMS/USSD (Phase 3):** Africa's Talking adapter; farmer USSD menu (check loan status, report production, view prices, confirm buyer offer); SMS alerts; OTP login.
- **M7 Reporting + Inputs + Intelligence (Phase 3):** scheduled donor/partner reports (PDF/Excel for PIND/GIZ-style indicators), input linkage with delivery confirmation, market intelligence (prices, supply-demand gaps), richer risk scoring.
- **M8 (Phase 4, design only):** document how yield prediction, satellite/weather feeds and credit-scoring models would plug in. Do not build them yet.

Start by building M0 and M1 only. Do not begin M2 until I have reviewed M1.

## 9. Offline sync design (M5, but design the API for it from M1)

- Client-generated UUIDs for all creatable records, so offline creation never collides.
- `POST /api/v1/sync/push` (batched, idempotent by `client_id` + operation id) and `GET /api/v1/sync/pull?since=<cursor>` (delta by `updated_at` cursor, scoped to what that officer is allowed to see).
- Tombstones for deletes, and explicit conflict responses carrying both versions.
- Photos upload separately and resumably, then attach by reference.
- The server validates everything the client sends. Never trust the client for permissions or scoping.

## 10. Data quality

- Required fields, range validation (e.g. pond size, stocking density, dates not in the future), and phone and NIN format validation.
- Duplicate-farmer check on registration with a "possible duplicate" review queue for DFAC.
- A data-quality dashboard: incomplete records, stale farms, outlier values, per-officer completeness.

## 11. UX principles

- Default to the simplest workable interface; assume low digital literacy and low bandwidth.
- Pages under ~150 KB where possible, large touch targets, clear status and sync indicators, and plain-language labels.
- Naira (₦) currency formatting, Africa/Lagos timezone, and Nigerian states/LGAs as reference data.
- English first. Structure i18n so Pidgin and local languages can be added later.

## 12. How I want you to work

1. **Before writing code:** read the framework document fully, then post a short plan: the stack confirmation, the milestone breakdown, assumptions, and any questions. Ask no more than 8 questions, grouped. Where the answer is unknown, state your assumption and proceed.
2. Work in small, reviewable commits with clear messages. Use feature branches per milestone.
3. Write tests alongside code. Permissions and decision-rule tests are mandatory, not optional.
4. Seed realistic Nigerian demo data (catfish farmers in Delta/Bayelsa/Rivers, a buyer, a lender, officers, trainers) via a `make seed` command so every portal can be demoed.
5. Keep `README.md`, `docs/architecture.md`, `docs/data-dictionary.md`, `docs/api.md`, `docs/rules.md` and ADRs current.
6. Never hard-code secrets. Use environment variables with `.env.example`.
7. If you must deviate from this prompt, write an ADR explaining why and tell me.
8. At the end of each milestone, report: what was built, what's tested, what's deferred, known risks, and the next step.

## 13. Definition of done (per milestone)

- `docker compose up` starts the full stack, and `make test` passes.
- Lint and type checks pass in CI.
- Migrations apply cleanly on an empty database and on seed data.
- The permission matrix test suite passes. No role can access anything outside its scope.
- Any new rule or alert has tests and is documented in `docs/rules.md`.
- The demo script in `docs/demo/` runs end to end.

## 14. Out of scope for now

Payment processing and bank integrations, a real credit-bureau integration, AI/ML models, satellite data, and a public marketplace. Design the extension points, but do not build them.

Begin now with step 12.1: read the attached framework and post your plan.
