# 0040 — Hiring belongs on the project

**Status:** accepted
**Date:** 2026-10-12

## Context

Everything needed to build a team on a project already existed and had done
for months: `Opportunity` carries a `project_id`, a student applies to an
opening, the person who posted it reviews the applications, and accepting one
with `add_to_project` calls `record_membership` — which puts the applicant on
the team *and* in its chat (ADR 0033).

None of it was reachable from a project.

Three separate things hid it, and each one alone was enough:

1. **The demo data never set `project_id`.** `seed_presentation_data.py` built
   nine openings and attached none of them to a project, so the section that
   lists a project's openings — which queries `?project_id=` — found nothing
   on every project on the platform and, correctly, rendered nothing. The
   deployed instance therefore showed a project page with a team, milestones
   and no way to join. Worse: `add_to_project` is a no-op when the opening
   names no project, so every seeded acceptance also left the applicant off
   the team they had just been accepted onto.

2. **A new opening is a DRAFT.** The section asked only for `status=open`, for
   its readers the right answer. For the lead it meant pressing "Post an
   opening", filling the form, and returning to a project page that still said
   there were no openings.

3. **A lead was never told anybody was waiting.** Application counts live
   behind `/opportunities/{id}/applications`, so the only way to learn that
   four people had applied was to open each opening in turn. Nothing on the
   project said hiring was happening at all.

## Decision

**A project page is where hiring on that project is run**, for both sides of
it, from one component and one request.

### 1. The two readers see different lists, from the viewer, not a flag

- The **lead** (the owner, holding `OPPORTUNITY_CREATE`) sees **every**
  opening on the project — draft, open, closed, filled — each with its state.
  The draft stage is load-bearing, so a view that hides drafts hides the thing
  the lead most needs to see.
- **Everybody else** sees only the **OPEN** ones. A draft belongs to its
  author and a closed opening is not a way in; listing either offers a door
  that does not open.

The section is called **"Hiring"** for the lead and **"Open positions"** for
everyone else, because the lead's list contains openings that are neither.

### 2. The counts are the poster's alone

`OpportunityCard` gains `application_count` and `pending_application_count`,
both `int | None`, and both filled **only when the viewer posted the opening**.
Everyone else gets `None`.

This follows `my_application_id`: a per-viewer field derived from the viewer,
never from anything in the request — the same discipline as `CREATABLE_ROLE`
and an announcement's audience. A student reading a project is deciding
whether to apply, and how long the queue is forms no part of that decision.

`pending_application_count` counts what is **not** decided, because "4
applications" and "2 waiting on you" answer different questions and only the
second is a prompt to act.

Zero is sent as `0`, never as `None`: "nobody has applied yet" and "we cannot
tell you" must not render the same.

### 3. "Post an opening" carries the project

The button links to `/opportunities/new?project_id=<id>` and the form
pre-selects it. Previously a lead who pressed it on their own project page had
to find that same project again in a dropdown, and choosing the wrong one
files the opening against the wrong team.

### 4. The seed attaches openings to projects, and repairs the ones it made

`_seed_opportunities` now hangs each school's openings off one of that
school's ACTIVE projects, with the **project's owner** as the creator —
because only `opportunity.created_by` may decide an application, and the
person adding somebody to a team should be the person whose team it is.

Rows that already exist are **repaired, not skipped**, the same reason
`_tag_project` runs for projects it did not create: a seeder that passes over
what is already there can never fix what it got wrong before.

Two further repairs fall out of the same run:

- Openings were seeded with one or two places and then filled by the seeded
  acceptance, so every one of them answered "All places taken" to every
  student who found it. A board where nothing can be applied for demonstrates
  the feature exactly as well as an empty one. Places were widened, and
  widening is safe in a way narrowing would not be — it can only ever leave
  more room than somebody has already been given.
- A seeded ACCEPTED application now also puts its applicant on the team,
  through `record_membership` and never a bare insert, so the chat is synced
  with the row. Writing the application alone left a demonstration in which
  somebody was accepted onto a project they were not a member of.

### 5. The other way onto a team was unreachable too

`POST /projects/{id}/members` has existed since projects were built, fully
enforced (`assert_owner`, and `record_membership` so the chat is synced), and
**nothing in the interface ever called it**. The frontend had `removeMember`
and no `addMember`. So the only way onto a team was to apply to an opening and
be accepted — no use at all for the colleague or the student a lead already
works with.

`AddMemberPanel` sits under the team for the lead: search, a role, add. It is
the `/admin/accounts/new` shape again — **enforcing a permission is not the
same as making it reachable**, and this is the second time that exact gap has
been found here.

Candidates come from the directory's own endpoints, so a student who has not
opted in to being discovered is not surfaced. That is the opt-in doing its job
rather than a gap: they can still apply, which is the other route. Somebody
already on the team is filtered out, so the picker cannot offer what the
submit would refuse — the rule the facility-custodian candidate list holds.

## Consequences

- No new endpoint, no new permission, no migration. The gap was never in the
  model; it was in what the interface asked for and what the demo data held.
- The member role an acceptance derives is now capitalised
  (`Research assistant`, not `research assistant`), because it is shown on the
  project page beside roles people typed themselves.
- Two optional fields on a hand-written TypeScript mirror, defaulted at every
  use for the Netlify-seconds/Render-minutes window, with a test that deletes
  them and asserts the section still renders — the same guard the dashboard's
  announcements panel carries.

## Alternatives rejected

**A separate "Recruitment" page per project.** A second place to look, and the
openings board already exists for browsing across projects. The project page
is where somebody asks "can I join this?", so that is where it has to answer.

**Showing application counts to everybody.** It reads as a feature and acts as
a deterrent: a student seeing "14 applications" on the one opening they were
qualified for does not apply. It is also not theirs to know.

**Letting a student apply inline, without opening the position.** The eligible
types, the deadline, the eligibility text and the lead's description are all
things somebody should read before applying, and an inline button invites an
application from somebody who has read none of them.

**Leaving the seed alone and documenting that openings must be linked by
hand.** The deployed instance is the demonstration. A feature that is correct
in the code and invisible on the screen has not shipped — the lesson
`_tag_project` and `MILESTONE_SHAPES` were both written to record.
