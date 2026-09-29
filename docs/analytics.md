# Analytics: what every number means

Each metric below states the query it comes from and, more importantly, what
it deliberately excludes. A figure without its rule invites the wrong reading,
and these numbers end up in a report somebody signs.

All analytics are **scoped**: a research coordinator sees their own
department, an administrator sees the institution. The scope is applied inside
each query (`insights.scope_for`), so it cannot be widened by a parameter.

---

## Publications

### Publications by department

```
count(distinct publication) grouped by the department of each linked author
```

A publication is credited to **every** department among its linked authors. A
paper co-authored across two departments counts once in each, so the column
sums to **more** than the total publication count.

That is the intended reading. The question a department asks is "how much did
we produce", not "how is a fixed total divided up".

**Excluded:** authors held only as text (`PublicationAuthor.external_name`)
have no account and therefore no department. The report states how many
publications could not be attributed rather than hiding the shortfall.

### Publications by year

The publication year on the record — the only date a bibliographic record
carries reliably. An academic year spans two calendar years, so two rows are
expected.

### Publications by venue

Top 20 by count. Records with **no** venue are omitted rather than bucketed as
"Unknown": an invented venue name in a report is worse than a shorter list,
and the total is reported separately.

### Publications by type

Grouped by `pub_type`. Every publication has one, so this partitions the total
exactly.

---

## Cross-department collaboration rate

```
rate = cross_department / (cross_department + same_department)
```

Computed over the `collaborations` pair table — accepted collaborations, not
requests.

- **cross_department** — the two people's departments differ
- **same_department** — they match
- **unknown_department** — at least one has no department

**Pairs with an unknown department are excluded from both halves** and
reported separately. Rolling them into the denominator would depress the rate
for a reason that has nothing to do with collaboration.

When nothing qualifies the rate is `null`, not `0`. No collaborations is not
the same as no cross-department collaboration.

---

## Application success rate

```
rate = accepted / (accepted + rejected)
```

Only **decided** applications are in the denominator.

| Status | In numerator | In denominator |
|---|---|---|
| Accepted | yes | yes |
| Rejected | no | yes |
| Submitted / Under review / Shortlisted | no | **no** |
| Withdrawn | no | **no** |

Pending applications have no outcome yet; counting them as failures would make
the rate fall simply because a reviewer is slow. Withdrawn applications were
stopped by the applicant, which is not a decision anyone made about them.

Zero decided applications yields `null`, not `0%`.

### A naming note

The specification calls this the "funding application success rate". This
platform's funding module is a **register** of calls with deadlines and saved
interest — it has no application workflow, and neither does the
specification's own M6. The applications measured here are therefore those to
**research opportunities** (M4). Stated plainly rather than relabelled to
match a heading.

---

## Milestone adherence

Counts outstanding milestones by derived risk (on track, due soon, blocked,
overdue) plus how many completed milestones finished on or before their due
date.

Risk is derived **when the query runs**, from status, due date and
dependencies — see ADR 0026 for why it is not stored. It therefore describes
the position *today*, not the academic year as a whole, and the report says so
beside the table.

---

## Equipment utilisation

Approved bookings only, with hours summed from the booking period. Pending and
rejected requests are excluded — a request nobody approved did not use the
equipment.

---

## Pre-existing metrics

`projects_by_status`, `projects_by_area`, `opportunity_funnel`,
`funding_interest`, `verification_backlog`, `trends` and
`collaboration_totals` are unchanged. Each is scoped the same way.

---

## Access

Every endpoint requires `Permission.ANALYTICS_READ`, held by research
coordinators and administrators. Faculty and students receive **403** —
verified by test against the API, not by hiding a menu item.
