# Implementation contract — FSP Vector

Date: 2026-10-07. Root owns integration, runtime, deployment, audits, release and top-level scripts. Project source remains local/private. Existing competitor snapshots are excluded from implementation.

## Decisions before scaffold

- Feature-first FastAPI modules and pure domain engines allow assessment, ranking and hiring to be tested independently.
- Next.js 16.4 / React 19.3 / TypeScript uses a typed fetch client with same-origin `/api/v1` proxy; OpenAPI export/codegen is part of integration.
- SQLAlchemy 2 works with PostgreSQL in the full local profile; SQLite is allowed only as a documented portable/test fallback. Root investigates portable PostgreSQL because Docker/WSL are unavailable.
- HttpOnly opaque server sessions with CSRF protection provide local auth; Keycloak OIDC adapter/profile is added without conflating identity with grade.
- SSE drives notifications; bounded polling is an explicit fallback.
- Consistent Problem Details errors, request IDs, explicit role/ownership checks and no-store private responses apply to every endpoint.
- User code is never executed in the Windows application. A safe data-oriented practical assessment is fully available; external Linux judge is configured separately and reports its real availability.

## Ownership / task list

| Agent | Assigned files | Deliverables |
|---|---|---|
| backend | `services/api/` except `app/engines/`, `services/api/tests/engines/` and `tests/evaluation/` | Domain models, migrations, feature services/routes, auth, profiles/PDF, survey/category/attempt lifecycle, employers/search/needs, invitations/grants, jobs/applications, FSP linking integration, challenges, inbox/SSE, ATS/outbox, role/privacy tests |
| frontend | `apps/web/` | Original visual system, landing/login/register/email states, both complete workspaces, assessment, passport, matching/filter/compare, invitations, jobs, practice, privacy, mobile and motion, real API integration |
| engines | `services/api/app/engines/`, `services/api/tests/engines/`, `evaluation/`, `assessment-bank/`, `data/` | Assessment families/blueprints/oracles and safe practical tasks, grade/cooldown functions, matching/extraction/FSP provenance, synthetic seed fixtures, independent evaluation reports |
| root | Everything else, coordinated integration fixes | Runtime/setup, portable database/identity, container profiles, client contracts, security and E2E audits, local start, docs and release |

Agents report API/core readiness early and send concrete contracts. No agent writes a completion claim before build/tests. Root performs integration audit after the first vertical path, privacy/domain audit after functional coverage and release audit after final changes.

## API conventions

Prefix `/api/v1`; snake_case JSON; string IDs; UTC ISO timestamps; `{items: [...], total: number}` for lists. Feature detail objects may extend these stable fields. Errors `{type,title,status,detail,code,request_id}`. Never return answers/oracle before assessment completion.

Auth:

- `POST /auth/register`: `{name,email,password,role,consent_processing}`; sends verification.
- `POST /auth/login`: `{email,password}`; sets session; returns me.
- `POST /auth/logout`; `GET /auth/me`.
- `GET /auth/verify?token=...`; local mailbox access is explicit demo-only.
- Me: `{id,name,email,role,email_verified,csrf_token,candidate_id,company_id}`.
- Demo accounts: `candidate@vector.local`, `employer@vector.local`, `employer2@vector.local`, password `VectorDemo2026!`, synthetic/local only.

Candidate:

- `GET/PATCH /candidate/profile`; `POST /candidate/resume-import`; `GET /candidate/profile.pdf`.
- Profile: `{id,name,alias,title,bio,city,specialization,declared_grade,confirmed_grade,category,score,skills,preferences,published,fsp,history}`. `skills` list of strings is declared; `evidence` is separate.
- Preferences: `{salary_from,salary_to,work_format,employment}`. Own contacts separate. Employer response never includes raw own contact fields.
- `POST /candidate/survey`: `{industry,specialization,grade,stack,work_format}`.
- `GET /candidate/dashboard`, `/candidate/passport`, `/candidate/history`.
- `POST /candidate/publication`: `{published,consent_publication}`; `GET/POST /candidate/consents`; `POST /candidate/contact-grants/{id}/revoke`.
- `POST /candidate/fsp/link`: `{fsp_id,proof_code}`; `DELETE /candidate/fsp/link`. Demo linking must validate identity, arbitrary IDs forbidden.

Assessment:

- `GET /assessments/catalog`; `POST /assessments/start`: `{specialization,grade,stack,demo:false}`.
- `GET /assessments/{id}`; `PUT /assessments/{id}/answers`: `{answers: {item_id: answer}}`.
- `POST /assessments/{id}/submit`: `{answers: {item_id: answer}}`; server persists and grades.
- Attempt: `{id,status,specialization,grade,expires_at,started_at,items,answers,result,policy}`.
- Item: `{id,title,prompt,type,competency,options,starter_code,public_cases,max_score}`; options `{id,label}`. Answer can be string/list/declarative JSON. No public oracle.
- Result: `{score,passed,competencies,practice_score,confirmed_grade,calibration_status,feedback}`.

Employer:

- `GET/PATCH /employer/company`; `GET /employer/dashboard`.
- `GET/POST /employer/needs`; `GET/PATCH /employer/needs/{id}`; `POST /employer/needs/extract`: `{text}`.
- Need: `{id,title,description,specialization,grade,skills,required_skills,salary_from,salary_to,work_format,employment,team,created_at}`.
- `GET /employer/categories`; `GET /employer/candidates` filters q/specialization/grade/skill/fsp_only/work_format/page.
- `POST /employer/matches`: `{need_id,filters}`; `GET /employer/matches/{id}`; `POST /employer/matches/{id}/refine`.
- Match: `{id,need_id,algorithm_version,items,total}`; each `{candidate,score,breakdown,reasons,gaps}`. Candidate projection includes alias/category/skills/evidence/achievements, only authorized contacts.
- `GET /employer/candidates/{id}`; comparison uses same candidate projection and need context.

Hiring:

- `GET /invitations`; `POST /invitations`: `{candidate_id,need_id?,vacancy_id?,title,message,salary_from,salary_to,work_format,employment,contact,expires_at?}`.
- `POST /invitations/{id}/accept`, `/decline`, `/withdraw`; `POST /invitations/{id}/messages`: `{text}`; `GET /invitations/{id}`.
- Invitation has company snapshot and salary; candidate accept transaction creates company-scoped grant. Repeat accept idempotent, competing withdraw safe.
- `GET/POST /vacancies`, `GET/PATCH /vacancies/{id}`; `POST /vacancies/{id}/apply`; `GET /applications`; `PATCH /applications/{id}` employer status.
- `GET/POST /challenges`; `GET /challenges/{id}`; `POST /challenges/{id}/submit`: `{answer}`; results never automatically change category.
- `GET /notifications`; `POST /notifications/read`; `GET /events` SSE.
- `GET /quality/summary` restricted operator/demo aggregate; `GET /health` and `/ready` top-level too.

## Design direction

**Current authority, 11 October 2026:** after rejecting the previous designs, the user authorized choosing and completing the entire website without another preview approval. Contra Hire is the single current layout and interaction reference. The implementation uses original Vector content, Lucide icons and an original glass V asset. Current typography, layout, motion and accessibility rules are in `DESIGN.md`; current verification is in `docs/audits/final-2026-10-11/contra-verification.md`. Figma C / Linear, Attio and the palette below are historical and superseded. Real persisted domain operations remain required.

Light workspace, ice lavender canvas `#F4F5FB`, white panels, deep ink `#1B1C21`, FSP violet `#402FFF`, red `#EC1D35`, verified emerald `#13866B`. Display: Manrope; body: Golos Text; data: JetBrains Mono, locally served if possible. Sidebar and content use dense but readable layouts; rounded corners 12–20px with restrained shadows.

Signature: a competence passport whose evidence rows connect to a need in the employer workspace, making the match tangible. Motion: coordinated entry, shared selection transitions, smoothly expanding evidence, invitation timeline and successful verification; no distracting animation during timed tasks. Respect prefers-reduced-motion.

Mobbin references inspected visually: Pin candidate requirements (`f92281c9-520c-47ed-884d-6f795cd03981`); folk hiring columns (`53ebff8e-b03e-4e7b-b85e-d1b3c14d8bfb`); Uxcel skill profile (`fd2a426b-3095-49b2-b0e5-2875263d76ff`); Asana step onboarding (`92e15ef9-4c99-4a1d-87eb-41a382fdae91`). Reference canonical links are kept in `docs/design-references.md`. Do not recreate their branding or screens verbatim.
