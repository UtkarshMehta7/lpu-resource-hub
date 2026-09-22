# ADR 0012: Step 11 facilities, equipment and booking

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** Step 11 adds the facility and equipment catalogue and a booking calendar whose central requirement is that two approved bookings of the same equipment can never overlap.

## Decisions

1. **The database prevents double-booking, not the service.** `bookings` carries
   `EXCLUDE USING gist (equipment_id WITH =, period WITH &&) WHERE (status = 'approved')`,
   which needs the `btree_gist` extension (enabled in migration 0011) to mix `=` on a uuid with `&&` on a range. No code path checks for overlap before writing; the service only translates the constraint violation into `409`. That is the only way two concurrent approvals can be made safe without locking the whole table.
2. **Pending requests may overlap freely.** Several people can ask for the same slot — that's normal — and approval is where the constraint bites. `tests/test_bookings.py::test_two_overlapping_approvals_cannot_both_succeed` runs two transactions that approve overlapping bookings at the same moment and asserts exactly one survives.
3. **Periods are half-open `[start, end)` `tstzrange` values**, so a booking ending at 10:00 and one starting at 10:00 do not overlap. The week calendar in the UI uses the same rule.
4. **Booking rules live on the equipment row** (`students_allowed`, `requires_approval`, `max_hours`, `min_lead_hours`, `maintenance_status`) and are enforced in the service: `403` for a student where students aren't allowed, `409` under maintenance, `422` for too long / too little notice / a start in the past. The frontend mirrors them for a fast error but never decides.
5. **`requires_approval = false` books outright** (status `APPROVED` immediately) and still goes through the same constraint, so instant booking can still lose a race and return `409`.
6. **Facility management is department-scoped.** `facility:manage` goes to coordinator and admin; a coordinator may only manage facilities in the department they oversee, and a create that names another department is refused (`403`) rather than silently moved. Out-of-scope management is `403`, not `404`, because the catalogue is public — hiding it would be pointless.
7. **Booking visibility is narrower than the catalogue.** A booking is visible to its owner, the coordinator whose department owns the equipment, and admins; anyone else gets `404`. Availability shows *periods only* — a slot says "booked" or "yours", never who booked it.
8. **`POST /bookings/{id}/complete` is a small addition** to the roadmap's approve/reject/cancel: without it the `COMPLETED` status would be unreachable. It's allowed for the owner or approver once the period has ended.
9. **Cancel only before the start** (`409` afterwards), for both pending and approved bookings.
10. **Lovely Professional University branding is now a standing frontend requirement.** `components/layout/Brand.tsx` holds the university name, the `LPU` shortform, the product name and the monogram; the header, footer, page titles and landing copy use it. The "Prototype" label stays attached to the mark and the demo-data disclaimer stays in the footer, because this is not an official university system.

## Consequences

- The exclusion constraint serialises approvals per equipment: two coordinators approving overlapping slots for the *same* item will have one wait briefly for the other. That's the intended trade-off, and different equipment never contends.
- `btree_gist` is left installed on downgrade: dropping an extension a later migration might depend on is riskier than leaving it.
- Availability is queried per week; a busy month view would want a coarser endpoint, which isn't needed yet.
- Times are compared in UTC throughout. A test that set a deadline with Postgres `CURRENT_DATE` (server timezone) rather than a UTC date was fixed in this step — the two differ for half the day in IST.
