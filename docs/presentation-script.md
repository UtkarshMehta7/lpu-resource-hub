# Presentation script — LPU Research Intelligence and Collaboration Hub

> **Prototype disclaimer.** This platform is a proposed/prototype system and is not an official
> Lovely Professional University system unless formally adopted or authorized. It is not connected
> to any real LPU system or data. Every person, project, publication, facility and funding record
> it shows is fictional demo data. Say this out loud early — it is on slide 1 of the deck for a reason.

This is the spoken script for the slide deck of the same name. The narration below is identical to
the speaker notes carried by each slide, so the two cannot drift apart.

## Timing

| Version | Slides | Roughly |
|---|---|---|
| Full walkthrough | all 35 | ~45 minutes speaking, plus questions |
| Department / review committee | 19 slides | ~20 minutes |
| Corridor / elevator | 6 slides | ~4 minutes |

**Cut-down slide lists**

- *Corridor:* slides 1, 3, 4, 5, 8, 35 — cover, what it does, the numbers, the architecture diagram, the sixteen capabilities, close.
- *Committee:* slides 1, 2, 3, 4, 5, 7, 8, 10, 14, 15, 18, 19, 21, 23, 26, 28, 31, 34, 35 — the opening, both enforcement diagrams, accounts, projects and their lifecycle, collaboration and its state machine, recommendations, facilities, analytics, deployment, quality, scope and close.

Delivery notes: speak the honest lines rather than skimming them — the prototype disclaimer, the
“route guards are tidiness, not security” line, the collaboration bug story on slide 18, and the
weakest-part answer in the Q and A. An audience trusts the rest of a talk in proportion to how
readily the speaker names its limits. Pause after each diagram before explaining it; let people
read the picture first.

---

## The script, slide by slide

### Slide 1 — Research Intelligence and Collaboration Hub
*Lovely Professional University (LPU) · prototype*

Good morning, and thank you for the time. What I am presenting is the LPU Research Intelligence
and Collaboration Hub: a working, deployed prototype, not a mock-up and not a slide deck with
nothing behind it. Everything you will see in the next half hour is running software with a real
database behind it. One honest thing before I start: this is a prototype I built, not an
official LPU system, and every person, project and record in it is fictional demo data. Nothing
here is connected to any live university system. With that said, let me show you the problem it
solves and how completely it solves it.

### Slide 2 — Research expertise stops at the department boundary
*The problem*

Here is the problem in four parts, and it is the same problem every large multi-school
university has. First, expertise is invisible across boundaries: a faculty member in the School
of Computer Science has no reliable way to find out who in the School of Aerospace is working on
the same optimisation problem. Second, equipment goes under-used, because the only people who
book an instrument are the people who physically walk past it. Third, funding calls close before
the people who could have won them hear about them. Fourth, students are shut out entirely: the
only route into a research project is already knowing someone inside it. Notice that none of
these are hard technology problems. They are visibility problems, and visibility is precisely
what a well-modelled database with correct permissions on top of it fixes.

### Slide 3 — Every person, project, lab and rupee of funding in one searchable place — and every action checked against who you are.
*What it does*

So here is the promise of the platform in one sentence. Every person, every project, every lab
and every rupee of funding lives in one searchable place, and every single action is checked
against who you are before it happens. Those two halves matter equally. A directory with no
permissions is a privacy incident waiting to happen. Permissions with no content is a locked
empty building. This system has 122 API operations across 39 database tables and 22 backend
modules, all governed by one permission map, and it costs nothing to run.

### Slide 4 — Not a demo — a system with a paper trail
*The build, counted*

Before the features, the evidence that this is engineering rather than a demo. 122 API
operations, every one of them permission-checked. 39 database tables, each arriving through one
of 21 reviewed, sequential, reversible migrations; the schema was never created by letting the
framework guess. 24 architecture decision records in the docs folder, one for every decision
that had a real alternative, so you can read why a choice was made and not just what it was. 459
backend test functions running against a real PostgreSQL database, not an in-memory substitute.
195 frontend tests, and 14 end-to-end flows that drive an actual browser against a live stack.
And the running cost is zero rupees, on free tiers, with no paid API anywhere.

### Slide 5 — Four layers, and each one only talks to the next
*Diagram 1 · System architecture*

This is the first diagram: the system architecture. Read it top to bottom. At the top the
browser runs a React 19 single-page application in strict TypeScript. It is served as static
files by Netlify, which also proxies every /api call through to the backend. That proxy is a
deliberate decision, not convenience: because the API answers on the same origin as the page,
the refresh cookie stays first-party and the session survives a page reload without relying on
third-party cookies that browsers now block. The third layer is the FastAPI application on
Render, and inside it there is a strict rule: routers speak HTTP and nothing else, services hold
the business rules and are forbidden from importing FastAPI at all, and policies answer
ownership and scope questions. That rule is what makes the rules testable on their own. At the
bottom is PostgreSQL on Neon, and it is a participant rather than a bucket: overlapping
bookings, duplicate collaborations and duplicate DOIs are refused by database constraints, not
by code that hopes to catch them first. And on the right, the point worth repeating: the
frontend guards nothing. Route guards hide menu items. Every decision is made again on the
server.

### Slide 6 — Open source, top to bottom
*The stack*

The stack, in one table, and the important column is the third one: why that choice. The backend
is Python with FastAPI, Pydantic for validation and SQLAlchemy with Alembic, which means the
schema changes as reviewable files rather than as a side effect. The database is PostgreSQL 18,
and we lean on it hard: full-text search, pg_trgm for typo tolerance, btree_gist for time-range
exclusion, and pgvector for embeddings. That is four capabilities that would otherwise be four
extra services to run and pay for. The frontend is React 19 in strict TypeScript with TanStack
Query holding server state and Zod validating every form. The matching is scikit-learn, which
runs locally, explains its own output and costs nothing. Quality tooling is ruff, mypy in strict
mode, pytest, eslint, prettier and Playwright, wired into four CI jobs that stand between any
change and the main branch. And hosting is entirely free tier. Docker exists but is optional, so
nothing here requires a licence or a credit card.

### Slide 7 — Who creates whom — and who checks it
*Diagram 2 · Roles and enforcement*

The second diagram answers the question every reviewer asks first: who can do what. On the left
is the provisioning chain, and it runs in exactly one direction. An administrator creates
coordinators. A coordinator creates faculty. Faculty create students. A student creates nobody.
Critically, the create-account request has no role field in it at all: the role is derived from
who is asking, so it cannot be forged. The one exception is a dedicated admin override endpoint,
which is audited under its own action name. Promoting somebody to administrator needs two
people: a code is sent to the target's own inbox. On the right are the three layers that enforce
all of this. Layer one is the screen, and I want to be blunt about it: route guards are
tidiness, not security, because a hidden button is still a reachable URL. Layer two is the API,
where one function checks one permission map on every operation, and where the role and the
active flag are re-read from the database on every request rather than trusted from the token,
so revoking a role takes effect immediately. Layer three is the data itself: policies for
ownership and department scope, and database constraints for the invariants that code should not
be trusted to remember. And at the bottom, the status codes are a design decision too: 401 means
you are not signed in, 403 means you are signed in but not allowed, and 404 means you must not
even learn that the thing exists.

### Slide 8 — Sixteen steps, each one shipped and checked in
*The sixteen*

The platform was built in sixteen numbered steps, zero through fifteen, and this is the map of
them. Each step was planned, approved, implemented on its own branch, tested, documented with a
decision record, and only then merged. I never worked on two at once and I never built ahead.
The next sixteen slides walk this grid in order, and I will show you what each one actually does
rather than just naming it. If you want to stop me anywhere and ask to see it running, please
do, because all of it is live.

### Slide 9 — A foundation you can argue with
*Step 00 · Foundation*

Step zero was not a feature, and I want to defend spending time on it. Three things were fixed
in writing before any feature existed. First, one error shape: every failure in the system
answers with the same envelope, a machine-readable code, a human message and a details object,
and it never leaks a stack trace, a SQL fragment or an internal path. That means the frontend
has exactly one error path to write and one to test. Second, one layering rule: routers speak
HTTP, services hold the business rules and are forbidden from importing FastAPI, and policies
answer ownership questions. Because that rule is mechanical it can be checked, so it does not
erode over sixteen steps the way a written-down convention usually does. Third, the checks ran
from the very first commit: ruff, mypy in strict mode and pytest against a real PostgreSQL
database, plus TypeScript, eslint, prettier and Vitest on the frontend. Adding quality tooling
at the end never works. Starting with it costs a day.

### Slide 10 — Nobody signs themselves up
*Step 01 · Accounts and sessions*

Step one is accounts, and the first design decision is the one people find surprising: there is
no public registration. A university already knows who its people are, so self-registration adds
nothing except a queue of unverified strangers. The endpoint POST /auth/register does not exist,
and there is a test that reads the API's own OpenAPI document and fails if such a path ever
reappears. Accounts come down the hierarchy instead: an administrator creates coordinators, a
coordinator creates faculty, faculty create students. The create request does not even have a
role field; the role is derived from the caller. On the session side, passwords are hashed with
Argon2id, which is the current recommendation rather than the fashionable one; a short fifteen-
minute access token sits beside an httpOnly refresh cookie that rotates on every use, and if an
old refresh token is ever replayed the whole family is revoked, which is how you detect a stolen
cookie. Finally there are two separate sign-in pages, administrators at slash admin slash login
and everybody else at slash login, and that separation is enforced on the server. The subtle
part is that the check runs after the password is verified, so the admin page can never be used
as an oracle to discover which registration numbers belong to administrators.

### Slide 11 — One map, and a memory
*Step 02 · Roles, permissions and audit*

Step two is authorisation, and the whole point is that it lives in one place. There is a single
map from role to permission in app slash core slash permissions dot py, and a single dependency
that enforces it. Nothing is scattered across route bodies, which is how authorisation bugs
normally happen. Two details matter. The role and the active flag are read from the database on
every request rather than trusted from the token, which means that deactivating an account or
demoting someone takes effect on their very next click, not when their token happens to expire.
And every sensitive action, role changes, approvals, verifications, deletions and admin
overrides, writes a row to an append-only audit log with the actor, the target, the action and
the time. Those rows are never updated and never deleted, because an audit log you can edit is
not an audit log. Backing all of it is a parametrised test that walks every role against every
guarded endpoint, so somebody adding a new route cannot quietly ship it without protection: the
matrix fails.

### Slide 12 — Everyone belongs somewhere
*Step 03 · Departments, taxonomy and profiles*

Step three is the organisational spine. Four schools, ten departments, and every account placed
in one of them. The important lesson here was learned the hard way: a coordinator's scope is
their department, and originally those two things could be set independently, which meant a
coordinator could be appointed and end up overseeing nothing at all. Now the scope is derived
and kept in step automatically whenever a role or a department changes, and the users page shows
each coordinator's scope so a missing one is visible instead of silent. Fixing the code was not
enough either; the coordinators appointed before the fix needed a data migration of their own.
The second piece is a shared vocabulary, because search only works if people tag things with the
same words: there are skills and a deliberately two-level research-area tree, with aliases so
that typing M L finds machine learning, and anyone may suggest a new tag which a coordinator
then approves or rejects. The third piece is verification. Faculty submit a researcher profile
and their own department's coordinator verifies or rejects it with a comment. Nobody can verify
themselves, not even a coordinator who is also faculty, and the decision is written to the audit
log.

### Slide 13 — Find the person, not the department
*Step 04 · Directory and search*

Step four is the directory, and it is the feature that answers the original problem statement.
One search box covers people, projects, opportunities, publications, facilities and funding
calls. Two decisions are worth pointing out. First, search is typo-tolerant: PostgreSQL's full-
text search ranks the real words, and pg_trgm trigram similarity catches the misspellings, so
somebody typing machine learning badly still finds the right researchers. Second, and this is a
subtlety that took a bug to discover, a registration number is not prose. Identifiers are
matched as a case-insensitive prefix, deliberately kept outside the language analyser, because
stemming somebody's UID produces nonsense. And on privacy: faculty are discoverable because that
is the point of a research directory, but a student appears only after explicitly opting in, and
that flag defaults to off. Discovery is opt-in for the people who did not sign up to be
discovered.

### Slide 14 — A project earns its visibility
*Step 05 · Projects and review*

Step five is research projects, and it is the first place a workflow appears. A project moves
from draft, to submitted, to under review, to active, to completed, and finally to archived. The
allowed transitions are written in exactly one table per workflow and enforced in the service
layer, which means the user interface cannot invent a shortcut and neither can a future
developer calling the API directly. The review is genuine: a coordinator opens a queue scoped to
their own department, and approves or requests changes with a comment that is recorded against
the project, so the author knows why. And projects have teams: members are added with a named
role, and visibility rules decide who may read a draft, who may read an active project and who
may edit. A draft is not public. That is what I mean by a project earning its visibility.

### Slide 15 — Every move a project can make, and no others
*Diagram 3 · Project review lifecycle*

This is the third diagram, and it is the project review lifecycle drawn in full. I want to be
precise about what this picture is: it is the contract. A transition that is not drawn here does
not exist in the service layer, which means it cannot be reached from the interface, cannot be
reached by calling the API directly, and cannot be reached by accident. Follow the top row: a
draft is visible only to its author; submitting it locks it for review; a coordinator reads it
under review; approving makes it active and visible according to the visibility rules; and
eventually it is completed with results recorded. Two branches come off the review box. The
orange line running back underneath is changes requested, which returns the project to draft
with the reviewer's comment attached. Downward is rejected, which is a state with a reason, not
a deletion. On the right, completed projects become archived, which is read-only history. Two
notes at the bottom. The review is department-scoped, and outside that scope the project answers
404 rather than 403, because the mere existence of a project is itself information a stranger
should not get. And nothing is ever deleted in order to move on: rejected and archived are
states, not absences, so the record, the reviewer and the comment all survive, which is what
makes the trail auditable a year later.

### Slide 16 — Research output, attributed properly
*Step 06 · Publications*

Step six is publications, and the interesting engineering is in a detail that most systems get
wrong. Author order is data, not a string. Each publication holds an ordered list of authors
that mixes platform users with external co-authors, so first-author position survives, which
matters enormously for the person being assessed on it. DOIs are unique, so two people cannot
each claim the same paper and a bulk import cannot quietly double somebody's count. And
publications are attached to the work: a paper shows up on every internal author's profile and
on the project that produced it, which is what lets the analytics later say something truthful
about output per project rather than just per person.

### Slide 17 — From a posting to a team member
*Step 07 · Opportunities and applications*

Step seven is the opportunity board, and this is the feature that answers the student half of
the problem statement. A posting moves from draft to open to either closed or filled, only the
owner moves it, and a closed posting stops accepting applications at the database level rather
than merely hiding a form. Applications themselves carry their own history: submitted,
shortlisted, accepted, rejected or withdrawn, each with who changed it and when. That timeline
is shown to the applicant, which sounds small but is the single most common complaint about
every application system anybody has used: silence. And the last card is my favourite bit of
design in this step: accepting an application adds the student to the project team in the same
database transaction. There is no second step for a busy supervisor to forget, and there is no
window in which somebody is accepted but not actually on the team.

### Slide 18 — One relationship per pair, guaranteed
*Step 08 · Collaboration*

Step eight is collaboration, and I am going to be honest about this one because it is the best
story in the project. The first version modelled a collaboration as a request from one person to
another. It worked, it passed its tests, and then in a demo two people who were already
collaborating were offered the option to collaborate again, and their conversation history split
in half. The instinct is to add validation. The correct fix was to change the model: a
collaboration is not a request, it is a relationship, and a relationship belongs to a pair. So
now there is one row per pair of people; a CHECK constraint forces the two user ids into a fixed
order, and a unique constraint on the pair means a duplicate cannot physically be written, no
matter what any future code does. Either partner may end the collaboration, which is audited,
and ending returns them to a state where they may collaborate again later without erasing the
fact that they once did. And requests are rate-limited to ten an hour per person, because a
collaboration request lands in a human being's inbox and so it deserves a human-scale limit.

### Slide 19 — Four states, held by the database and not by hope
*Diagram 4 · Collaboration state machine*

The fourth diagram is the collaboration state machine, and it is small on purpose. There are
four states. None means the two people have no relationship. Requested means one has asked and
is waiting. Active means they are collaborating and a shared conversation is open between them.
Ended means they were collaborating and are no longer, with everything preserved. The arrow
underneath is declined or withdrawn, going back to none. The arrow over the top is the one that
matters for usability: the same pair may collaborate again after ending, which is a normal thing
for two researchers to do. Now the three notes along the bottom, because these are the
engineering claims. First, a duplicate is not merely validated against, it is unrepresentable: a
CHECK constraint forces user A's id to be lower than user B's, and a unique index covers the
pair, so there is exactly one row per pair of human beings and no code path can create a second.
That is arithmetic, not vigilance. Second, there is one conversation thread per pair, and it
opens with the collaboration and outlives it, so history never splits across attempts, which was
the original bug. Third, ending is not erasing: either side may end it, both keep the record and
the messages, and they may collaborate again later.

### Slide 20 — One thread, for as long as the pair exists
*Beyond the roadmap · Messaging*

Messaging came after the sixteen steps, and it exists because collaboration without a way to
talk is just a contact list. Three things about it. The conversation is keyed to the pair of
people rather than to a request, which is the direct consequence of the earlier fix: it opens
when they connect and it stays readable after they have finished, so there is one continuous
history between any two people. The paging is a keyset cursor over the message's timestamp and
id rather than an offset, which means that when new messages arrive while you are scrolling, the
list never skips one and never shows one twice; offset paging quietly does both. And
notifications collapse per conversation rather than firing once per message, so the bell icon
still means something when it lights up. I should be transparent that this is also where I
learned a hard lesson: an early notification type had no display case written for it, so the
code was delivered and invisible while every test passed. Tests passing is not the same as the
screen working, and since then every new piece of interface gets driven in a real browser before
I call it done.

### Slide 21 — A suggestion that can say why
*Step 09 · Explainable recommendations*

Step nine is the matching, the part people mean when they say AI, and I want to set expectations
honestly. There is no large language model and no paid API. There are two signals. The first is
tag overlap: shared skills and shared research areas between two people, or between a person and
a project. The second is TF-IDF text similarity over titles and abstracts, computed with scikit-
learn inside the same process. The two are combined and weighted. What makes it usable rather
than mystifying is the third card: every suggestion lists the shared tags and the shared terms
that produced it, so a researcher can look at a recommendation and decide in two seconds whether
it is real. An unexplained ranking gets ignored; an explained one gets clicked. And because a
recommender that cannot be measured cannot be improved, there is an evaluation set in docs slash
ai-evaluation dot md with recorded precision at k, so any change to the ranking can be shown to
help or to hurt rather than argued about.

### Slide 22 — Each role opens on its own work
*Step 10 · Dashboards, saved items and moderation*

Step ten was the MVP milestone, where the pieces became a product. The key idea is that a shared
dashboard serves nobody: so there are four genuinely different front pages. A student lands on
their applications and their suggested opportunities. Faculty land on their projects and the
work waiting for them. A coordinator lands on their department: the verification queue, the
review queue, their people. An administrator lands on the platform itself. Alongside that, one
saved list covering projects, opportunities, researchers and funding calls, because the thing
you meant to come back to should be in one place and not four. And a reporting route on any
content, which opens a moderation queue item whose decision is recorded in the audit log with
the moderator who made it. Moderation without accountability is just a delete button.

### Slide 23 — Equipment that cannot be double-booked
*Step 11 · Facilities and booking*

Step eleven is facilities and equipment booking, and it contains the single best example in this
project of why the database matters. Two people click book at the same instant for the same
microscope. Application-level checking cannot reliably stop that, because between the check and
the write there is a gap, and under load something eventually slips through it. So the
constraint lives in PostgreSQL: a btree_gist exclusion constraint over the booking's time range
means an overlapping row is physically rejected on insert. One of the two requests fails,
cleanly, and we show that person why. Around that there is a real catalogue: facilities, the
equipment inside them, a maximum booking length per item, and an approval step where the owner
wants one. And a calendar showing availability by day with your own bookings marked, where a
conflict is explained rather than silently swallowed. This is the feature that answers under-
used equipment in the problem statement.

### Slide 24 — Deadlines that come to you
*Step 12 · Funding and notifications*

Step twelve is funding calls and notifications, and it closes the third gap in the problem
statement: missed deadlines. Funding calls are first-class records with an organisation, an
amount, eligibility and a closing date, and they sit in the same search index as people and
projects rather than in somebody's forwarded email. The notification design is worth a sentence:
notifications are event-driven, meaning the service that actually causes a thing writes the
notification in the same transaction. There is no background job scanning the database trying to
work out what changed, which is how systems end up announcing the same thing twice or missing it
entirely. And reminders go out before a closing date, not after, which sounds obvious but is
precisely the failure being fixed: a deadline you hear about afterwards is not information, it
is regret.

### Slide 25 — Meaning as well as words
*Step 13 · Semantic search*

Step thirteen adds semantic search, so that somebody searching for drone navigation finds a
project described as autonomous aerial path planning even though not one word matches. The
embeddings come from sentence-transformers and are stored in pgvector, which is an extension
inside the same PostgreSQL database. That is a deliberate cost and complexity decision: there is
no separate vector service to run, secure, back up or pay for. The ranking is hybrid: lexical
and semantic scores are combined, so an exact term still wins when it deserves to and meaning
only decides the near-ties. And I will point at the third card honestly, because it is a real
constraint rather than a feature: the machine-learning extra is not installed in production,
because the model weights exceed what a free instance can hold. The platform runs completely
without it and falls back to lexical search, which means the free deployment is genuinely free
rather than quietly requiring an upgrade.

### Slide 26 — What the university can finally see
*Step 14 · Analytics and network*

Step fourteen is analytics, and it is the slide for the reader who has to report upward.
Projects, publications, applications and bookings, over time, grouped by school and by
department. Then the collaboration network: who works with whom, drawn from the accepted
collaborations, which is the picture that shows whether cross-department collaboration is
actually happening or whether everybody is still talking to the person next door. And the audit
log gets a user interface, so an administrator filters by actor and by action in the browser.
That last one matters more than it looks: an audit log that only a developer with database
access can read is a compliance ornament. Making it readable is what turns it into a control.

### Slide 27 — A free tier, properly hardened
*Step 15 · Deployment and hardening*

Step fifteen was not a feature, it was making the system safe to expose to the internet. The
headers first: content security policy of default-src none on API responses, HSTS in production,
nosniff, framing denied, no referrer, and a requirement that every browser request carries an
X-Requested-With header, which a cross-site form cannot set, so that is the CSRF defence
alongside an explicit CORS allowlist. Rate limits are per route: five login attempts a minute,
sixty searches a minute, ten collaboration requests an hour. Supply chain checks run in
continuous integration and again weekly, because a dependency does not become vulnerable when
you touch it, it becomes vulnerable while you sleep; that is pip-audit, npm audit and a gitleaks
scan across the full git history, not just the latest commit. And migrations: every schema
change is a reviewed, sequential, reversible file, and the deployment applies them and then
reports the result on the readiness endpoint, so if the schema is behind the code the service
says so out loud instead of pretending to be healthy. That took several failed deploys to get
right, and the fix that finally unlocked it was putting the migration state into the health
probe, so I could see the real problem from outside without a database credential. Interactive
API documentation is switched off in production.

### Slide 28 — Live on three free tiers, and nothing else
*Diagram 5 · Deployment topology*

The fifth diagram is the deployment topology, and I like this slide because the whole thing
costs nothing. At the top is GitHub, and the arrows out of it only fire after four continuous-
integration jobs pass, so a red build never reaches either host. Netlify takes the static site.
Render builds the API as a Docker image with the backend folder as its root directory. Along the
bottom row is the request path: a browser talks to Netlify, Netlify serves the page and forwards
every slash api call to Render, and Render talks to Neon, which is PostgreSQL 18 with pgvector.
The proxy is the interesting decision, and it is on the left-hand note. If the API lived on its
own domain, the refresh cookie would be a third-party cookie, which modern browsers block, and
sessions would silently stop surviving a reload. Proxying through Netlify keeps it first-party.
A practical scar from that: the netlify.toml file has to sit at the repository root, because
Netlify will never look anywhere else for it, and I lost time to that. On the right, migrations
are applied from a workstation as a reviewed release step. And the bottom right note is the
current state: the site is live at lpu-research-hub.netlify.app in front of the API on Render
against Neon, and health, readiness, sign-in and the production security headers have all been
verified on the deployed instance rather than assumed.

### Slide 29 — Six corrections that only a real user finds
*After v1.0.0 · what the demos taught us*

Version one point zero was not the end, and this slide is the part I would want a reviewer to
read. These six corrections all came from putting real people in front of the thing, and none of
them would have been found by a test. The registration number now appears wherever a person is
named, through one shared component, because with thirty-four demo users there were already name
collisions. Deleting and deactivating turned out to be two different needs: deactivate somebody
who has left, delete an account that should never have existed, which frees the registration
number. Because twenty-one of the thirty-one foreign keys pointing at a user cascade, a deletion
is costed first and the impact is shown before it is confirmed. Coordinator placement is derived
and now visible on screen, so a coordinator overseeing nothing is obvious rather than silent.
The two sign-in pages are enforced server-side, after the password, so neither page becomes a
way to guess who is an administrator. Every confirm dialog is centred, which sounds trivial
until you open the platform on a phone. And faculty can now reach their department's coordinator
in one click, with the verification queue linking through to the person being reviewed. The
honest summary of this slide is that tests passing is not the same as the screen working.

### Slide 30 — 39 tables, and all of them lead back to a person
*Diagram 6 · Entity relationships*

The sixth and last diagram is the data model, grouped rather than drawn table by table, because
thirty-nine boxes would be unreadable on a screen. In the centre, in orange, is the users table,
and the number on it is the one to remember: thirty-one foreign keys point at a user. That
single fact explains several design decisions elsewhere, most obviously why deleting an account
has to be costed and shown before it is confirmed, since twenty-one of those thirty-one cascade.
Around the centre are six groups. Organisation is schools and departments, which is where every
account is placed. Research is projects, their members, publications and author positions.
Connection is the collaboration pairs, the conversations and the messages. Taxonomy is the
shared vocabulary of skills and research areas with aliases and suggestions. Opportunity is
postings, applications and the status events that form an application's timeline. Resources is
facilities, equipment, bookings and funding calls. And underneath is the platform layer:
notifications, saved items, content reports and the append-only audit log. Every one of these
tables arrived through a reviewed migration; none of them was created by letting the framework
guess at the schema.

### Slide 31 — How we know it works, rather than believe it
*Quality*

This is the slide I would ask for if I were assessing someone else's project, so here it is
unprompted. The backend runs ruff, mypy in strict mode and pytest, and the tests hit a real
PostgreSQL database with each test rolled back afterwards, not an in-memory stand-in, because
half of what this system relies on is PostgreSQL-specific and an in-memory database would test
nothing that matters. That is 459 test functions across 47 files. The frontend runs TypeScript,
eslint, prettier and Vitest, at 195 tests. Then fourteen Playwright flows drive an actual
browser through the real application across three different roles. The schema layer is worth a
moment: after applying the migrations we run alembic check, which proves that the migration
history and the model definitions still agree, and that check has caught real drift in this
project more than once. Security scanning is pip-audit, npm audit and gitleaks across the full
git history. All of it is four CI jobs on every push, and main is green. I will also say what
this does not prove: tests do not prove the screen is usable, which is why the last slides
showed six things only real use found.

### Slide 32 — Assume the network is hostile
*Security posture*

The security posture in six parts, and the framing is the first line: assume the network is
hostile, because it is. Identity: Argon2id password hashing, fifteen-minute access tokens beside
a rotating httpOnly refresh cookie, and if an old refresh token is replayed the whole family is
revoked, which is how a stolen cookie is detected rather than merely survived. Authority: one
permission map, per-module ownership policies, and the role and active flag re-read from the
database on every request. Transport: a content security policy of default-src none on API
responses, HSTS in production, nosniff, framing denied, no referrer and a tight permissions
policy. Forgery: every browser request must carry an X-Requested-With header, which a cross-site
form is not able to set, alongside an explicit CORS allowlist. Abuse: rate limits scoped per
identity and not merely per address, because per-address limits are trivially defeated. And
disclosure: one error envelope that never carries a stack trace, SQL or an internal path,
interactive documentation switched off in production, and 404 returned wherever a 403 would leak
the existence of something. None of this makes a prototype bank-grade, and I would want a proper
review before real data went anywhere near it. But the shape is right.

### Slide 33 — A populated university, entirely fictional
*The demonstration instance*

A demonstration is only convincing if the screens have something in them, so the platform is
seeded with a whole fictional university. Four schools: Computer Science and Engineering,
Management, Architecture, and Aerospace and Aeronautical Engineering, each with its own
departments. Thirty-four accounts across every role, from administrators down to students, each
one placed in a real department and carrying a registration number, so you can sign in as any of
them and see the platform exactly as that person sees it. Every screen has content behind it:
projects at every status including ones sitting in the review queue, publications with proper
author ordering, opportunities with real applications against them, facilities with bookings,
funding calls, active collaborations and message threads with history. And the third card on the
bottom row is the one I will not skip past: every single record is fictional. The names are
generic, the projects are invented, and nothing is connected to any LPU system. That disclaimer
is at the top of the README and in the documentation, not just in my speech.

### Slide 34 — What it is, what it is not, what comes next
*Being precise about what this is*

I want to be precise about scope, because overclaiming is the fastest way to lose a room. What
it is: a complete, deployed and tested platform covering discovery, projects, opportunities,
publications, collaboration, facilities, funding, matching and analytics, documented to a
standard where somebody else could take it over, which is the real test of whether a student
project is engineering. What it is not: an official university system. It is not connected to
any real LPU data, it holds fictional records only, and before that changed it would need a
proper security review and a data-protection sign-off. I would not want it used with real
people's records on my say-so alone. And what comes next if there is appetite for it: single
sign-on against the university directory so nobody manages another password, a pilot with one
school rather than a big-bang rollout, an import of real projects and publications to give the
matching something true to work with, and paying for infrastructure only at the point where the
free tier genuinely stops being enough.

### Slide 35 — The expertise was always there. Now it can be found.

I will finish where I started. Nothing in this presentation created new research expertise at
the university; the expertise was always there. What was missing was the ability to find it, and
that is a solvable problem, so I solved it. Sixteen steps, 122 API operations, 39 tables, 24
decision records, 654 automated tests, 14 browser flows, live on free infrastructure at zero
rupees a month. It is running right now at lpu-research-hub.netlify.app, and I am happy to open
any screen you would like to see, sign in as any role, or walk through any part of the code.
Thank you for your time, and I would welcome your questions.

---

## Live demonstration run sheet

Nine moves, about twelve minutes, in this order. Sign-ins are on the deployed instance; every
account is fictional.

| # | Move | Where | What to point at |
|---|---|---|---|
| 1 | Sign in as a student | /login with a student registration number | The dashboard opens on their applications and their suggested opportunities — note the registration number beside every name. |
| 2 | Search across everything | One search box | Type a misspelled research term and it still finds the right people. Then type a registration number and watch it match as an identifier, not as prose. |
| 3 | Open a researcher profile | From the directory | Verified badge, skills, research areas, publications with author order, and their department's coordinator one click away. |
| 4 | Apply to an opportunity | Opportunity board | Submit, then show the status timeline the applicant sees. |
| 5 | Switch to the coordinator | Sign out, /login as a coordinator | Verification queue and project review queue, both scoped to their department. Approve one with a comment. |
| 6 | Request a collaboration | From a researcher profile | Send it, accept it from the other side, show the shared message thread, then end it and show that the history survives. |
| 7 | Book equipment | Facilities → a facility → equipment | Book a slot, then try to book an overlapping one and show the conflict being refused. |
| 8 | Show the analytics | Dashboard → analytics | Output by school and department, and the collaboration network. |
| 9 | Sign in as the administrator | /admin/login — note the separate page | Users with scopes visible, the audit log with filters, and the deletion-impact screen without confirming it. |

If something fails live: say so plainly, note that the deployed instance runs on a free tier that
sleeps when idle, and move to the next move rather than debugging in front of the room. A failed
demo that is named is forgivable; a speaker fighting a laptop is not.

---

## Questions to expect, and the answers

**Is this an official LPU system?**

No, and I want that on the record. It is a prototype I designed and built. It is not connected
to any LPU system and it holds no real university data. If the university wanted to adopt it,
that would be a formal decision with a security review and a data-protection sign-off attached,
and I would expect both.

**Where does the data on screen come from?**

A seed script in the repository. Four fictional schools, thirty-four fictional accounts,
invented projects, publications, facilities and funding calls. The names are generic on purpose.
Nothing on screen describes a real person or a real project.

**What does it cost to run?**

Zero rupees a month as it stands: Netlify, Render and Neon free tiers, with no paid API
anywhere. The matching runs locally with scikit-learn rather than calling a paid model. Where it
would eventually cost money is the semantic-search extra, because the embedding model exceeds a
free instance, and a paid instance if concurrency grew. Both are deliberate: the platform runs
fully without either.

**Is it secure enough for real student records?**

Not without a review, and I would not claim otherwise. What is already in place is Argon2id
hashing, short-lived tokens with rotating refresh cookies and reuse detection, one permission
map enforced on the server, per-identity rate limits, a content security policy, CSRF
protection, an append-only audit log, and dependency and secret scanning in CI. That is the
right shape. It is not a substitute for somebody independent looking at it.

**Why can people not register themselves?**

Because a university already knows who its people are, so self-registration would only produce a
queue of unverified strangers to sort out. Accounts come down the hierarchy instead: an
administrator creates coordinators, a coordinator creates faculty, faculty create students. The
create request has no role field at all, so a role cannot be forged, and there is a test that
fails if a public registration endpoint ever reappears.

**Is the AI part ChatGPT, or some paid model?**

Neither. There are two local signals: tag overlap between people, projects and areas, and TF-IDF
text similarity over titles and abstracts computed with scikit-learn inside the same process.
Later, sentence-transformers embeddings stored in pgvector add semantic matching. Nothing leaves
the server and nothing is billed. Every recommendation also shows the shared tags and terms that
produced it, which is the part that makes people actually trust it.

**What happens if two people book the same instrument at the same moment?**

One of them fails, cleanly, and is told why. The rule is not in the application code, where
there is always a gap between checking and writing: it is a btree_gist exclusion constraint in
PostgreSQL over the booking's time range, so an overlapping row physically cannot be inserted.

**Can a coordinator see another department's projects or people?**

No. Their scope is their own department, and it is derived from their department record rather
than set by hand, so the two can never drift apart. Outside that scope a record answers 404
rather than 403, because the existence of a project is itself information a stranger should not
be handed.

**How do you know it works, rather than believe it?**

459 backend test functions run against a real PostgreSQL database with each test rolled back,
195 frontend tests, and 14 Playwright flows that drive a real browser across three roles against
a live stack. After migrations run, alembic check proves the models and the migration history
still agree, and that has caught real drift here. Four CI jobs gate every push and main is
green. I will also say what tests do not prove: they do not prove the screen is usable, which is
why several fixes in this project came from watching a person use it.

**What happens when a faculty member leaves the university?**

You deactivate them, which takes effect on their very next request because the active flag is
read from the database rather than trusted from their token. Deleting is a different action for
a different need: an account that should never have existed, where deleting frees the
registration number. Because twenty-one of the thirty-one foreign keys pointing at a user
cascade, a deletion is costed first and the full impact is shown before anybody confirms it.

**Why PostgreSQL rather than a document database?**

Because most of the hard guarantees in this system are relational or constraint-based: one
collaboration per pair, no overlapping booking, one DOI claimed once, author order preserved.
Those are constraints, and PostgreSQL enforces them for free. It also gave me full-text search,
trigram fuzzy matching, time-range exclusion and vector search in one service I already had to
run, which is four services I did not have to add.

**Could somebody else take this over?**

That was a design goal. There are 24 architecture decision records, one for every decision that
had a real alternative, so a new developer reads why and not only what. The schema exists as 21
sequential reviewed migrations rather than as a database somebody has to reverse-engineer. The
layering rule is mechanical, the API is documented by its own schema, and the CI configuration
means a newcomer's first pull request is checked the same way mine was.

**What is the weakest part of it today?**

Three things, honestly. There is no single sign-on yet, so it manages its own passwords, and in
a real deployment it should not. Semantic search is switched off in production because the model
does not fit a free instance, so what is live is lexical plus tag matching. And it runs as a
single instance, so it is sized for a pilot with one school, not for the whole university on day
one. None of those are unknown unknowns, which is the point.

**How long did this take, and how was it built?**

In sixteen numbered steps, zero through fifteen. Each one was planned and approved before any
code, built on its own branch, tested, documented with a decision record, and only then merged.
I never built ahead of the current step. The parts I am proudest of are the corrections after
version one, because those came from putting people in front of it and finding what the tests
could not.

---

## Facts card — keep this in view while speaking

| | |
|---|---|
| Roadmap steps complete | 16 (steps 0–15), v1.0.0 |
| API operations | 122, every one permission-checked |
| Database tables | 39, across 21 reviewed sequential migrations |
| Backend modules | 22 |
| Decision records | 24, in `docs/adr/` |
| Backend tests | 459 test functions across 47 files, on a real PostgreSQL database |
| Frontend tests | 195 |
| End-to-end flows | 14, Playwright, across three roles |
| CI | 4 jobs per push, green on main |
| Demo instance | 4 schools, 10 departments, 34 accounts, all fictional |
| Hosting | Netlify → Render → Neon, all free tier |
| Live | lpu-research-hub.netlify.app in front of lpu-resource-hub.onrender.com |
| Running cost | ₹0 per month |

Roles, in one line each: **administrator** runs the platform and is the only role that may name a
role; **research coordinator** owns one department — verification, project review, its people;
**faculty / researcher** owns projects, publications, opportunities and facilities; **student**
discovers, applies, collaborates and books.

