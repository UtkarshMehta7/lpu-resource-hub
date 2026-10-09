# AGENTS.md: LPU Research Intelligence & Collaboration Hub

## What this is
Prototype research discovery & collaboration platform for the LPU ecosystem.
NOT an official LPU system unless formally adopted or authorized.
All data is fictional demo data. Never present fabricated data as real LPU data.

## Source of truth
- docs/architecture.md (approved architecture): follow it, don't redesign it.
- docs/adr/: record every significant decision as a new ADR (000N-title.md).
- README roadmap table: one step at a time. NEVER build ahead of the current step.
- lpu-roadmap-prompts.md: the full step-by-step roadmap and per-step prompts.

## Stack (do not replace)
Backend: Python 3.12+, FastAPI, Pydantic v2 / pydantic-settings, SQLAlchemy 2.0 (sync) + psycopg 3, Alembic
DB: PostgreSQL 16+ only (never SQLite). Uses FTS, pg_trgm, btree_gist, pgvector later.
Frontend: React 19 + TypeScript strict, Vite, Tailwind 4, React Router, Axios, TanStack Query, RHF + Zod
AI: scikit-learn (TF-IDF) now; sentence-transformers + pgvector later. Local only, no paid APIs.
Tooling: ruff, mypy --strict, pytest | eslint, prettier, tsc

## Hard rules
- Zero cost. No paid APIs, no mandatory cloud, Docker optional only.
- RBAC is enforced on the BACKEND. Frontend guards only hide UI.
- Role/active status always loaded from the DB, never trusted from token/client.
- 401 = not authenticated; 403 = authenticated but not allowed; 404 = must not know it exists.
- Never commit secrets or .env. All config via env vars; .env.example has placeholders only.
- Every schema change = reviewed Alembic migration with sequential rev id (--rev-id 000N).
  Never use Base.metadata.create_all().
- Separate Create/Update/Response Pydantic schemas. role, owner_id, status are never client-writable.
- Routers: HTTP only. Services: business rules, no FastAPI imports. Policies: ownership/scope.
- Workflow status transitions defined in ONE table per workflow and enforced in services.
- Business APIs under /api/v1. Errors use envelope {"error":{"code","message","details"}}.
- Sensitive actions (role change, approvals, deletions, admin actions) write to audit log (from Step 2).
- No new dependency without a stated purpose. No `any`, no broad `# type: ignore`,
  no disabling lint rules to pass checks.
- Tests use a real PostgreSQL test DB (TEST_DATABASE_URL), each test rolled back.
- Don't claim something works unless you ran it. Unverified = say "NOT VERIFIED".

## Where this actually is (read before planning anything)
All 16 roadmap steps are done (v1.0.0), plus the corrections after them:
department placement (ADR 0018), the provisioning hierarchy (ADR 0019), the
admin console, and the deployment configuration.
**Do not restart the roadmap or rebuild working modules.**

Current shape: 174 API operations over 140 paths, 48 tables, 33 migrations,
37 ADRs, 28 backend modules, 1215 backend tests, 316 frontend tests,
14 Playwright flows.

## Accounts and provisioning (the part most often got wrong)
- Nobody self-registers. `POST /auth/register` does not exist and must not
  come back; a test asserts the OpenAPI document has no such path.
- `CREATABLE_ROLE` in `app/core/permissions.py` is the only authority on who
  creates whom: admin -> coordinator -> faculty -> student.
- The create-account request has **no `role` field**. The role is derived
  from the caller. Never add one back "to validate it".
- `POST /api/v1/admin/users` is the admin override, audited under its own
  action. That is the only place a role may be named **in a request**.
- **A coordinator appoints facility custodians** (ADR 0030), through
  `POST /api/v1/facility-custodians` -- a route whose role is a CONSTANT, not
  a field. `CREATABLE_ROLE` still maps every role to exactly one successor,
  which is what lets an ordinary appointment derive its role from the caller;
  a second successor would have forced a `role` field back into the body.
  `CUSTODIAN_APPOINTERS` says who may call it, and a custodian is absent from
  it on purpose -- looking after rooms must not confer the power to mint
  peers. Scope is the coordinator's own department, same as for faculty.
- Promoting to admin takes two people: a code goes to the *target's* inbox.
- **A coordinator's scope IS their department.** `_sync_coordinator_scope`
  keeps them in step whenever the role or department changes; they must never
  be set independently by hand again, or the coordinator oversees nothing.
- **Two sign-in pages, enforced on the server.** `LoginRequest.portal`
  ("admin" | "main"): administrators only at /admin/login, everyone else only
  at /login. The check runs *after* the password, so the admin page can never
  become an oracle for which numbers are administrators.
- **Demo accounts carry LPU-shaped registration numbers** in the 125xxxxx
  block (`demo.faculty07@example.com` -> `12500207`), derived from the email
  by `_demo_registration_number` so the seed stays idempotent and the rebrand
  script agrees with it. They used to be `DEMOFACULTY07`, which was obviously
  fake on purpose; `users.is_demo` carries that meaning now. Hand-made
  accounts live in 124xxxxx, so the blocks never collide. **The E2E flows sign
  in with these numbers** -- change the scheme and `frontend/e2e/flows.spec.ts`
  changes with it, or CI goes red at sign-in.
- **A person's DEPARTMENT is shown wherever they are named**, as a name and
  not a UUID: `department_name` rides beside `department_id` on researcher
  cards, the researcher page and student cards, looked up once per page. The
  researcher card used to show no department at all.
- **The registration number is the UID and is shown wherever a person is
  named** -- via `components/ui/Uid`, never a hand-rolled span. Every
  person-bearing response schema carries `registration_number`; search matches
  it as a case-insensitive prefix, not through the language analyser -- an
  identifier is not prose.
- **Deleting is not deactivating, and both are needed.** `DELETABLE_ROLES`
  in `app/core/permissions.py` says who may remove whom: admin anyone but
  themselves, coordinator their department's faculty and students, faculty
  their students, student nobody. Nobody deletes their own account, which is
  also why no "last administrator" check exists -- it would be unreachable.
  21 of the 31 FKs to `users.id` CASCADE, so a deletion is always costed
  first (`GET /users/{id}/deletion-impact`) and shown before it is confirmed.
  Deactivate for someone who has left; delete for an account that should
  never have existed (it frees the registration number).
- **A PATENT is not a publication** (ADR 0035), and it is its own table for a
  reason that is not taste: analytics counts `publications` with no type
  filter in nineteen modules, so an eighth `PublicationType` would have folded
  patents into every publication figure on the platform. It also has a
  lifecycle the office drives (filed -> published -> granted, or
  rejected/withdrawn/lapsed), numbers that mean nothing outside their
  jurisdiction, and an assignee. **Inventors, not authors** -- a legal word on
  a patent, so the shared list widget takes a `noun` rather than being copied.
- **An invention is filed WITH the university, not only recorded after**
  (ADR 0036, amending 0035). Four stages sit in front of FILED --
  `disclosed -> under_assessment -> approved_to_file | declined` -- and
  `filing_date` is NULL for all of them, because the office issues it. ONE
  record, one pipeline: a separate disclosures table splits one invention
  across two rows and then has to answer which row owns the inventor list.
  `already_filed` on create chooses between exactly two entry points and is not
  a status field by the back door.
- **Two actors on the patent pipeline, and the order of the checks matters.**
  The university's half is the IP cell's, the office's half is the inventor's
  to record. A move that does NOT EXIST is 409 whoever asks; a move that exists
  but is somebody else's is 403. Checked in that order, or an inventor is told
  that `granted -> disclosed` is merely above their pay grade.
  `next_statuses` is computed per reader, so the interface cannot offer a step
  the service would refuse.
- **`public_disclosure_date` is the field that earns the feature.** A paper,
  poster, thesis or demo before filing is the commonest way a university loses
  patent rights outright. Captured at disclosure and flagged on the record and
  in the queue -- with wording that sends the question to the IP cell, because
  grace periods differ sharply between offices and this platform is not
  qualified to say which applies. Declining REQUIRES a reason, in the service
  and as a CHECK: "no" without one is what stops the next person disclosing.
- **A CHECK cannot reference an enum value added in the same transaction.**
  Postgres refuses the literal ("new enum values must be committed before they
  can be used"), so migration 0033's constraints compare `status::text`. That
  is what keeps the pipeline in one migration instead of two. `op.drop_constraint`
  takes the BARE name -- the naming convention adds the `ck_patents_` prefix,
  and passing the full name yields `ck_patents_ck_patents_...`.
- **Two workflows run on a patent and they are kept apart.** `status` is what
  the patent OFFICE did; `verification_status` is whether this institution has
  checked the RECORD. A granted patent can still be entered with the wrong
  numbers. Collapsing them would say a coordinator's approval and a grant were
  the same event. A status claiming an event carries that event's date, as a
  CHECK and as a sentence -- the milestones' "done is never undated" again.
- **Students may record patents, and that is the point** (`PATENT_CREATE` is
  the first thing a student may create). Student inventors are ordinary here.
  The safeguard is the approval queue, not withholding the form. A dean and a
  custodian may NOT -- ADR 0028 makes both deliberately read-only -- but either
  can still be NAMED as an inventor, so nobody loses the credit.
- **Prior art says what it did NOT search.** No open worldwide patent register
  can be read without a key: EPO OPS 403, USPTO 401, PatentsView retired its
  keyless endpoint, PATENTSCOPE 403, PQAI 401. All tested, not assumed -- the
  ADR 0025 wall again. So the check does three honest things: looks for the
  same invention already recorded here, searches the open literature (a paper
  is prior art, and OpenAlex and Crossref are keyless), and hands the query to
  the registers that can answer it. The panel states it has not searched the
  world, and a test asserts that sentence exists. An unreachable source is
  REPORTED **by name** (ADR 0037) -- a short list read as a clean result is
  the worst thing this feature can produce, and "one of the indexes" withholds
  the one fact that says how big the hole is. OpenAlex and Crossref do not
  cover the same ground. `unavailable_sources: list[str]`, never a boolean,
  and never a second derived flag beside it. `SOURCES` fixes the order and the
  zip is `strict=True`, so a third source added without extending it fails
  loudly rather than mislabelling which one was down.
- **The two prior-art lookups run concurrently, with their own budget.**
  Crossref's `query.bibliographic` regularly exceeds ten seconds, which is the
  whole budget the frontend's HTTP client gives the request, so sequential
  calls could never both fit and the slow one always lost. Six seconds each in
  parallel; that one request also gets a longer client timeout, because it is
  a deliberate act with a spinner on it.
- **Reusing an enum means `create_type=False` in the migration.** `patents`
  reuses the profiles' `verification_status` rather than minting a second one
  saying the same four words. Autogenerate does not know that and emitted a
  CREATE TYPE, which fails against any database that already has profiles.
  The downgrade must drop the type the migration DID create, or a downgrade
  then upgrade fails the same way.
- **Chat must never break collaboration.** Opening a thread on acceptance
  runs in a savepoint and swallows SQLAlchemyError: the acceptance is the
  older, more important act. Shipping the code before its migration made
  every acceptance answer 500 -- an additive feature took down an
  existing one. A new dependency from old code to new code gets the same
  treatment.
- **A collaboration is a PAIR, not a request** (ADR 0023). `collaborations`
  stores user_a_id < user_b_id under a unique constraint, so a duplicate is
  impossible in the database rather than guarded in a service somebody can
  forget. One conversation per pair, for the life of the pair: collaborating
  again after ending reopens the same thread. Never key a thread or a
  relationship to a request again.
- **Joining a team joins its chat, and ONE place writes both** (ADR 0033).
  Three paths made somebody a `ProjectMember` and only two synced the thread:
  accepting an application inserted the row itself, so being approved into a
  project put you on the team and left you out of its chat. `record_membership`
  and `discard_membership` in `projects/service.py` are now the only writers,
  and each syncs with the insert. Never write `ProjectMember` anywhere else.
  The bug only bit when the thread already existed, because opening one later
  syncs from `ProjectMember` regardless -- which is to say it bit exactly the
  active teams that had been talking.
- **A project gets its thread when it is CREATED**, with the creator in it.
  It used to appear on first use, so a new project looked like it had no chat.
  `_open_team_thread` runs in a savepoint and swallows SQLAlchemyError, like
  the acceptance path: chat must never break the older act. No backfill was
  needed, because `open_for_project` is still idempotent.
- **An attachment IS a message** (ADR 0033), which is what makes it small:
  the participant check, the closed-thread refusal, unread counts, the rate
  limit and the notification already existed and all apply. There is also no
  moment when uploaded bytes have no owner, so nothing to reap.
- **An attachment's bytes are on its own row, and the download runs the
  thread's check.** Bytes in `message_attachments.data`, not a shared blob
  table -- a shared table wants de-duplication, and that means blobs
  outliving their attachment, orphaned against a 0.5 GB quota. There is **no
  public path to a file**: a private thread is worth nothing if its files are
  reachable by whoever holds a URL, so `GET /conversations/{cid}/attachments/
  {aid}` re-checks participation, scopes the id to the conversation in the
  path, and refuses a hidden message's file. Hence the frontend fetches bytes
  through the API client and hands itself the download -- an `<a href>` sends
  no Authorization header, which is the point.
- **An upload's type comes from its BYTES** (`uploads/validation.py`). The
  filename and the browser's Content-Type are both attacker-chosen, so a RAR
  called `report.pdf` is stored and labelled as a RAR. A `.docx` is a zip, so
  only its table of contents separates them -- read without touching an
  entry's data, so a bomb has nothing to expand into. PDF, DOCX, PNG, JPEG,
  RAR, ZIP; 5 MB (`UPLOAD_MAX_BYTES`), checked on bytes read, never on a
  declared length. **No EXIF stripping and no virus scanning** -- revisit
  before building profile photos on these rules.
- **Threads are scoped, and there is no endpoint that creates one.** A
  conversation belongs to an accepted collaboration request or a project
  team; it appears when that happens. Never add a create-conversation
  route, or the student opt-in (`can_contact`) is repealed by the back
  door. A non-participant always gets 404, never 403 -- admins included.
  New messages arrive by polling, not sockets (ADR 0022): the cursor is a
  keyset over (created_at, id), never an offset.
- **An academic year is not a calendar year.** July to June by default,
  `ACADEMIC_YEAR_START_MONTH` configurable. "2025-27" is refused as a typo
  rather than reinterpreted -- a wrong period on a signed report is worse
  than an error message. See app/modules/analytics/academic_year.py.
- **The institutional report has ONE aggregation, three renderings** (JSON,
  CSV, PDF from the same `InstitutionalReport`). Never add a second
  aggregation for a format; the numbers would drift.
- **A dean compares DEPARTMENTS; that is the job.** `scope_for` answered
  either "one department" or "the whole institution", so the one question a
  Dean of Research actually asks had no answer -- a single blended total hides
  exactly what it is wanted for. `GET /analytics/by-department` puts them side
  by side, and `?department_id=` narrows the overview. An institution-wide
  reader may narrow to any department; a coordinator asking for somebody
  else's gets 403, never their own figures quietly substituted.
- **A metric that cannot be computed reads "not applicable", never 0.** No
  decided applications is not a 0% success rate. Every rate returns None
  rather than dividing by zero, and every table carries its definition --
  see docs/analytics.md for the formulas.
- **An administrator needs no verification, ever.** Verification means
  somebody senior vouched for a record, and nobody is senior to an admin --
  a PENDING admin was asking a coordinator to vouch for their own senior, and
  the queue had no role filter so they really appeared there. Four guards,
  because any one alone leaves a gap: the profile verifies itself on save,
  the queue excludes admins whatever their stored status, `/verify` refuses
  them (409, and rejecting is the dangerous half), and an import does not
  reset them. Migration 0025 fixed the rows already deployed.
- **A name search NEVER picks a person** (ADR 0027). It offers candidates
  with their institution, metrics and a link to the record, and the
  researcher chooses; the choice comes back as `openalex_author_id` and beats
  any matching. Taking `results[0]` is how a live user imported Nitish
  Srivastava of Google as themselves.
- **Importing sends a verified profile back to PENDING.** A tick means
  somebody here checked the record; after an import it holds claims nobody
  here has seen. Never let an import preserve verification.
- **Every imported work links to its DOI** so it can be checked before it is
  accepted, not audited afterwards. `WorkCandidate.url` is the fallback.
- **A collaboration suggestion is about the GAP.** `_collaborator_candidates`
  excludes anyone with an open or accepted request *and* anyone the viewer has
  already co-authored a publication with -- suggesting a long-standing
  co-author is the one recommendation a researcher is certain they did not
  need. The notification rides the same scoring as the page, so the two can
  never disagree, and its dedupe key is the ordered pair, so two people are
  introduced once ever.
- **A dean decides work that CROSSES departments** (ADR 0032), and nothing
  else. `review_queue` scopes a coordinator to one department, so a project
  whose team reaches into a second had no reviewer who could see all of it --
  a hole in the model, not an invented gate. `may_review` in
  `projects/policies.py` holds the rule, not the permission: holding
  PROJECT_REVIEW says a person may review *a* project, never every project.
  "Crosses" is computed from the team, never flagged. The queue filters
  through the same function the decision uses, or it is a dead button.
- **Every role needs a dashboard section**, or it signs in to a blank page.
  The dean and the custodian had none for days. `analytics/service.py:dashboard`
  dispatches per role; add a section there when a role is added.
- **One nudge travels DOWNWARD, and only one** (ADR 0031).
  `PROJECT_AT_RISK` is a dean or admin saying "somebody else's project is
  slipping, please look at it"; every other kind is "my own thing is stuck"
  and its resolver refuses an entity the sender does not own. Don't add the
  dean to the existing kinds -- the ownership checks would refuse them, and
  rightly. Its guards are the sender being in `INSTITUTION_WIDE_ROLES` and the
  project actually being in trouble, asked of the same `assess` the board
  uses. The notification reads "asked you to look at", not "is waiting on" --
  identical wording inverts who owes whom.
- **Nudges never name their recipient.** `POST /nudges` takes a kind and an
  entity; the service resolves who hears about it from the thing being
  chased. A recipient field would make it a way to message anyone in the
  institution, and a test asserts the schema has exactly two fields. One
  nudge per thing per day, enforced in the service, not the interface.
- **A milestone's risk is DERIVED on every read, never stored** (ADR 0026).
  `milestones/risk.py` is a pure function of status, due date, today and what
  it waits on; the analytics view calls that same function rather than
  reimplementing the rules in SQL. Never add an `at_risk` column -- a stored
  flag is wrong between job runs, and the board would disagree with the
  project page. The scheduled job exists only to notify exactly once.
- **Milestones have two actors, not one.** Members may move work along
  (`in_progress`, `done`); only the owner may create, edit, delete or cancel.
  `milestones/policies.py:TRANSITIONS` is the single table both are checked
  against.
- **Milestone visibility is composed, not restated.** A milestone is visible
  exactly when its project is, so the service calls
  `projects.service._load_visible`; one on an invisible project is a 404.
  Don't grow a second copy of the visibility rule.
- **Dependency cycles are refused in the service**, not the database: no
  constraint can express acyclicity, and a cycle makes the risk walk
  non-terminating. Self-dependency is the one case a CHECK does catch.
- **The seed script creates projects and milestones now.** It previously
  created none, so any plan that says "add X to the demo projects" should
  check they exist first.
- **Profile import pulls from four public sites, and none of them is the one
  the brief names** (ADR 0025). ORCID resolves identity, OpenAlex supplies
  breadth in place of Scopus, Crossref canonicalises metadata by DOI, and
  Semantic Scholar adds abstracts best-effort. Scopus and Web of Science need
  a paid licence; ResearchGate answers a server-side request with 403 and a
  CAPTCHA; JSTOR has no profiles to import and no API; DBLP serves an anti-bot
  page. All four rejections were tested, not assumed -- don't re-litigate them
  from the brief's list.
- **Import is preview-then-apply, and apply re-reads the sources.** Never
  change it to trust the payload the browser sends back: that would let any
  account post arbitrary publications labelled as imported from Crossref.
- **A DOI is normalised before it is compared or stored** (`normalise_doi`).
  OpenAlex percent-encodes the slash on some records, and one malformed DOI
  makes Crossref reject the entire 40-item batch it appears in. Found live.
- **Two different DOIs are never merged, however alike the titles.** An
  erratum, a preprint and its version of record are separate works. The
  de-duplication rules and their known failure cases are written up in
  `docs/publication-deduplication.md`.
- **The duplicate review queue has a floor, not a band** (ADR 0029). It asks
  a person about everything from `TITLE_SUGGEST_THRESHOLD` (84) **upwards**,
  including identical records scoring 100 -- the importer only de-duplicates
  what it sees in one pass, so a hand-typed paper and the same paper imported
  a month later are two stored rows it never had the chance to merge.
  `TITLE_MATCH_THRESHOLD` (92) governs the *importer's* licence to act
  unattended, which is a different question. Don't restate them as two edges
  of one band -- the first ADR draft did, and it was wrong. It reuses
  `merge.py`'s rules rather than growing a second opinion, so the DOI veto
  holds in both places.
- **The scan shortlists in the DATABASE, then scores in Python.** Postgres
  generates candidate pairs with the trigram index on `publications.title`
  (`a.title % b.title`, `a.id < b.id`), and rapidfuzz scores only what comes
  back -- the same division the import path has always used. Comparing
  everything with everything in Python gets the same answer and stops being
  free as the register grows; a test asserts the shortlist loses no pair the
  exhaustive comparison finds.
- **A merge DELETES the losing publication; it does not hide it.**
  Publications are read in fifteen places across eight modules, and a
  hidden-row flag would have to be honoured by every one -- one missed query
  is a ghost publication that still answers a search. The deleted row is
  snapshotted on the review row, which is what makes the merge reversible; an
  undo recreates it with a **new id**. Never add a `merged_into_id` column to
  `publications`.
- **A decided duplicate pair is never raised again by a later scan.** If
  "these are different works" came back next week, the queue would never empty
  and people would stop reading it.
- **Six roles, and two of them inherit nothing.** `FACILITY_CUSTODIAN` and
  `DEAN_OF_RESEARCH` (ADR 0028) sit outside `CREATABLE_ROLE` entirely: they are
  appointed only through the admin override, whose permitted set is
  `APPOINTABLE_BY_ADMIN` -- every role but `ADMIN`, because promotion stays the
  two-person ceremony. A custodian's scope is a **set of facility rows**, not a
  department, so `facility:manage` is checked object-level against the loaded
  facility (`facilities/policies.py: may_manage_facility`); the same rule as a
  query filter is `manageable_facility_filter`, and the booking queue uses it so
  a listing can never show a request the approve call would then refuse. A dean
  holds `analytics:read` and nothing else, and `INSTITUTION_WIDE_ROLES` is why
  they alone need no department.
- **Enforcing a permission is not the same as making it reachable.** The
  custodian role shipped fully enforced and *unassignable*: `custodian_id` was
  in no schema and no endpoint wrote it, so the role could be created and
  never used. The tests passed because the fixture wrote the column with raw
  SQL. A fixture that reaches past the API hides exactly that gap -- if a
  helper needs SQL to set something up, ask which endpoint is missing.
- **Holding a facility and deciding who holds it are different powers.**
  `PUT /facilities/{id}/custodian` is gated at DEPARTMENT level
  (`assert_can_manage`), never object level: a custodian passes the object
  check for their own facility, so folding the assignment into
  `FacilityUpdate` would let them hand the room away or take a colleague's.
  The candidate list (`/custodian-candidates`) is filtered by the same rules
  the assignment enforces, so the picker can never offer somebody the
  assignment would refuse. Both directions audited.
- **A facility's department decides who can manage it ever after**, so the
  create form makes it an explicit choice and refuses to submit without one.
  It used to send `user.department_id` for an administrator -- which is null,
  because an administrator belongs to no department -- so every facility an
  admin created came out university-wide, reachable by no coordinator and
  counted in no department's figures. "University-wide" is still offered, as a
  deliberate option that says what it costs.
- **A seed that matches on registration number also OVERWRITES the role.**
  `seed_presentation_data.py` matched a number that already belonged to a
  coordinator, changed them to a custodian and left the old
  `coordinator_scope_id` behind -- the exact inconsistency
  `_sync_coordinator_scope` prevents inside the application, reintroduced from
  the side. A script writing directly to the database carries the invariants
  the services carry. Check **roles**, not just names, before running a seed
  against a populated database.
- **A seeded project needs TAGS, not just a team.** `_seed_projects` was
  handed the school's skills and areas and used neither, so
  `project_research_areas` was empty and the dean's "projects by area" panel
  rendered blank on the deployed instance -- that panel counts through that
  table. Tagging is its own idempotent step (`_tag_project`) that runs for
  projects which already exist, because a seeder that skips what is already
  there can never repair what it got wrong before.
- **Demo milestones need more than one SHAPE.** Give every project the same
  chain with an overdue milestone in front and `blocked` beats `at_risk`
  (ADR 0026), so the deployed board showed `at_risk: 0` and `on_track: 0` --
  the at-risk board demonstrating the state it is named after not at all, and
  P08 acceptance criterion 4 unshowable. `MILESTONE_SHAPES` rotates four:
  slipping, due soon, healthy, finished. A dependency only blocks when it is
  itself overdue or at risk, so what sits *in front* of the outstanding work
  is what decides.
- **The demo seed creates facilities and equipment now**, and assigns the
  first to `demo.custodian01` (12500401); `demo.dean01` (12500501) has no
  department, as a dean must not. Before this the catalogue, the booking queue
  and the custodian role were all empty on a fresh install.
- A fix to the service layer does not fix the rows already in the deployed
  database. The coordinators appointed before `_sync_coordinator_scope` needed
  migration 0018 as well, and the users page now shows each coordinator's
  scope so a missing one is visible instead of silent.

## UI conventions (white + LPU orange, tokens in frontend/src/index.css)
- **A `<select>` whose value is not among its options shows the FIRST one.**
  `ROLE_OPTIONS` on the accounts page was a second hand-written list beside
  `ROLE_LABELS`, and it fell behind when the custodian and dean arrived: every
  dean and custodian row read "Student", and saving that row would have
  demoted them. Derive such a list from the `Record<Role, …>` map so the
  compiler refuses a missing case; never maintain two lists of the same thing.
- **One button recipe:** `components/ui/buttonClass` + `Button`/`ButtonLink`.
  Never hand-write `rounded-md bg-brand-700 px-3 py-2 ...` again.
- **One page top:** `components/ui/PageHeader` (title, one-sentence
  description, actions). 50 pages had rolled their own.
- **A page reachable from one tile is still missing.**
  `/admin/accounts/new` -- the override, and the ONLY way to create a facility
  custodian or a dean -- was linked from a tile on `/admin` and listed
  nowhere, so it was absent from the top bar, the full menu and the command
  palette, and people reported the feature as missing. A link on a page is
  not a substitute for an entry here.
- **`components/layout/navigation.ts` is the single list of destinations.** It
  drives the top bar, the grouped "All pages" menu and the command palette, so
  a role can never reach a page through one and not another. Add a page there
  or it is unreachable from two of the three.
- **Cmd/Ctrl+K (or "/") opens the command palette.** 28 destinations, six fit
  on the bar; the palette is how people actually get around. It only offers
  pages the signed-in role can reach.
- Loading shows `SkeletonList`, not the word "Loading".

## Gotchas that cost real time here
- **A new module's models must go in `app/db/model_registry.py`** or
  autogenerate produces an **empty migration** and says nothing is wrong. It
  did exactly that for `publication_duplicates` the first time.
- **A nested path loses to a path parameter registered before it.**
  `/publications/duplicates` was swallowed by `/publications/{publication_id}`
  and "duplicates" was parsed as a UUID, because FastAPI matches in
  registration order. Give a new resource its own top-level path
  (`/publication-duplicates`) rather than relying on include order in
  `app/main.py`, which breaks silently when somebody reorders it.
- **A mutation calls its `mutationFn` with more than one argument.** Passing
  an api function by reference (`mutationFn: undoDuplicateMerge`) forwards all
  of them; wrap it (`(id) => undoDuplicateMerge(id)`) or a
  `toHaveBeenCalledWith` assertion fails for reasons that look like the click
  never happened.
- **Don't reuse a label for a filter and an action on the same screen.**
  "Different works" was both a status chip and a button, so four tests matched
  the wrong element -- and a reader would have had the same trouble.
- **Refresh is single-flighted across TABS, not just within one** (ADR 0034).
  Refresh tokens rotate and re-presenting a rotated one revokes the whole
  family, which is how a stolen token is contained. `refreshPromise` in
  `lib/api/client.ts` dedupes inside one tab; the cookie is shared by all of
  them, so two tabs waking together both POSTed it and the second was read as
  replay -- signing both out mid-use, with nothing on screen to explain it.
  That was the "unexplained session expiry". `navigator.locks` now serialises
  them. Never refresh from outside that lock, which is exactly how it was
  finally caught.
- **Autogenerate does not see enum values.** It compares tables, not enum
  members, so `ALTER TYPE ... ADD VALUE IF NOT EXISTS` is written by hand
  (migrations 0017, 0019). A test DB already stamped at that revision will
  not pick it up -- rebuild it rather than debugging the enum error.
- **Tests passing is not the screen working.** The OTP code was delivered and
  invisible because `describeNotification` had no case for it, and every test
  passed. Drive new UI in a browser before calling it done.
- **Walk it from empty.** Every deadlock found here was a bootstrapping gap,
  not a permission bug. `tests/test_bootstrap_walkthrough.py` is the guard.
- **`getByLabel` substring-matches.** "Search" matched the brand link;
  "Name" matched a "Rename X" button. Use `{ exact: true }` or a role.
- **The frontend TS types are hand-written mirrors of the Pydantic schemas**
  and have drifted twice. When adding a backend field, update
  `frontend/src/features/*/types.ts` in the same change.
- E2E runs against the *development* database, so its state matters. A
  local run needs `scripts/seed_demo_data.py` first, or every flow fails
  at sign-in for want of the seeded admin (12500001) -- CI seeds it, a dev
  box may not.
- **The E2E sign-in helper has to use the right entrance.** Administrators
  are refused at /login (ADR 0020), so `sessionFor` sends the seeded admin
  (12500001) to /admin/login. This is what turned CI red for six commits, unnoticed
  because the other five jobs stayed green. Anchor the URL assertion
  (`/\/admin$/`): an unanchored `/\/admin/` also matches /admin/login, so
  a failed sign-in passes and the test dies later, somewhere confusing.
- **The `e2e` label needs `types: [... labeled]` on the workflow.** The
  default `pull_request` types are opened/synchronize/reopened, so adding the
  label fired nothing and the Playwright job only ran after an unrelated push
  -- an opt-in nobody could opt into.
- **Check `gh run list` after pushing.** Backend and frontend passing is
  not the suite passing.

## Deployment (configured, never yet performed)
Free path: Neon (Postgres + pgvector) -> Render (API from source, reads
`render.yaml`) -> Netlify (static, reads root `netlify.toml`, proxies /api
so the refresh cookie stays first-party).
- `netlify.toml` MUST be at the repo root; Netlify never finds it elsewhere.
- Render's Docker runtime looks for `./Dockerfile` at the configured root
  directory -- set that to `backend`, or use the Blueprint for a source build.
- **The deployed instance migrates itself at boot** and starts degraded if
  that fails, reporting why on /health/ready (ADR 0024,
  on by default in production). No advisory lock: DATABASE_URL is Neon's
  *pooler*, PgBouncer in transaction mode, where a session-level
  pg_advisory_lock is never released -- the container hung before binding its
  port and the deploy was cancelled. Nothing that runs before the port is
  bound may be able to block.
- Still run **destructive or data-rewriting** migrations deliberately with
  `backend/scripts/release.sh` before merging the code that needs them.
  Unattended is fine for adding a table; it is not fine for merging rows.
- Do not install the `ml` extra in production; it exceeds a free instance.
- **Deployed 24 Sep 2026.** API live on Render (Docker service, root
  directory `backend`) against Neon; health, readiness, login and the
  production headers all verified. Netlify still to do.
- The Docker images HAVE now been built, by Render. Never built locally.

## Commands
Backend (backend/, venv active): ruff check . && ruff format --check . && mypy && pytest
Run: uvicorn app.main:create_app --factory --reload
Migrate: alembic upgrade head
Frontend (frontend/): npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build
Run: npm run dev

## Workflow for every step
1. Read AGENTS.md, docs/architecture.md, and the step prompt.
2. Give a concise PLAN (files, models, endpoints, migrations, tests, deviations). STOP for approval.
3. Implement only that step on branch feat/step-N-<name>.
4. Run all checks + the step's verification list. Fix root causes.
5. Update README status/roadmap, docs/architecture.md if needed, add ADR if a decision was made.
6. Report: summary, files, deps, migrations, endpoints, checks (PASSED/FAILED/NOT VERIFIED),
   deviations, commands to run, next step. Then STOP.
