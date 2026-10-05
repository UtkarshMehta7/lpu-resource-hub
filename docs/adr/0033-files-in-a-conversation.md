# ADR 0033: Files in a conversation

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

A research team that cannot send each other a paper is not collaborating; it
is announcing. Threads carried text only, so the actual artefacts — a draft
PDF, a figure, a dataset — went through WhatsApp, and the record of the work
lived somewhere the platform could not see.

Two things had to be decided: where the bytes live, and who may read them.
The second turned out to be the harder one.

## Decision

### The bytes live in PostgreSQL, on the attachment row

Not an object store, and not a shared blob table.

- **Not local disk.** Render's filesystem is ephemeral and this instance
  redeploys on every merge to `main`. Files written there vanish, silently,
  at the least convenient moment.
- **Not Cloudflare R2 yet.** It is the right long-term home — 10 GB free and
  no egress charge — but it needs an account, credentials in the environment
  and an S3 client. `CLAUDE.md`'s rule is "no mandatory cloud", and a feature
  that cannot be run by cloning the repository fails it.
- **Not a shared `stored_blobs` table.** A shared table invites
  de-duplication by hash, and de-duplication means a blob outliving the
  attachment that pointed at it: an orphan nobody is counting against a
  0.5 GB quota. On the attachment row, the existing foreign key does the
  work — delete the message, the thread, the project or the person and the
  bytes go with them, by the same cascade as everything else in this schema.

The cost of this decision is stated plainly: **5 MB per file, against a
0.5 GB database.** That is roughly a hundred files before it matters, which
is right for a prototype and wrong for a campus. R2 is the migration when
that day comes, and the only thing that changes is where `data` is read from.

### The type comes from the bytes, never the name

`uploads/validation.py` sniffs magic bytes. The filename and the browser's
Content-Type are both chosen by the uploader, so neither decides anything:
an archive uploaded as `report.pdf` is stored, served and labelled as an
archive. Handing a browser a file under an extension it is not is how an
upload becomes something else.

Accepted: PDF, DOCX, PNG, JPEG, RAR, ZIP. ZIP rides along with RAR
deliberately — RAR is proprietary and a recipient on macOS, iOS or Android
generally cannot open one without installing something first, so accepting
only the format people *cannot* open would be a strange place to land.

A `.docx` IS a zip, so the signature cannot separate them and the table of
contents has to. Only the central directory is read, never an entry's data,
so a zip bomb has nothing to expand into.

### A file IS a message

`POST /conversations/{id}/attachments` creates a message carrying the file,
with the draft text as its caption. This is the decision that made the rest
small: the participant check, the closed-thread refusal, the unread counts,
the rate limit and the notification all already exist and all apply
unchanged. There is also no window in which uploaded bytes exist without an
owner, so there is nothing to collect later.

### Downloads run the same check as the thread

This is the part that matters. A thread is private — a non-participant gets
404, administrators included — and that is worth **nothing** if the files in
it are reachable by whoever holds a URL. So there is no public path to an
attachment at all: `GET /conversations/{cid}/attachments/{aid}` re-checks
participation, scopes the attachment to the conversation in the path, and
refuses a hidden message's file.

The consequence reaches the frontend: a plain `<a href>` carries no
Authorization header, so the browser fetches the bytes through the API
client and hands itself the download. That is a small inconvenience standing
in for a real guarantee.

Served `Content-Disposition: attachment` with `nosniff` always, so nothing
shared in a thread is ever rendered on this origin.

### A project gets its thread when it is created

Previously the thread appeared on first use, so an abandoned draft carried no
empty conversation. That saved two rows and cost the thing people actually
expect: you make a project and its chat is there, with you in it. Two rows is
the cheaper side of that trade.

Guarded by a savepoint like the acceptance path: chat must never break the
older, more important act. `open_for_project` stays idempotent, which is why
projects that predate this need no backfill.

## Consequences

- One new dependency, `python-multipart`. Starlette parses
  `multipart/form-data` only when it is installed, and a `File()` route
  raises at import time without it — a hard runtime dependency, not an extra.
- `MessageRead` grew `attachments`, and the frontend mirror grew with it in
  the same change, as that mirror has drifted twice before.
- Hiding a message now withholds what was shared as well as what was said.
  Hiding the text and leaving the file downloadable would be no moderation.

## What was deliberately not done

- **No EXIF stripping.** A JPEG shared in a thread keeps its metadata,
  including GPS coordinates. Stripping it means decoding untrusted images,
  which is a larger attack surface than the one it closes, and it would need
  Pillow. Acceptable for a file shared deliberately with named collaborators;
  **not** acceptable for a public profile photo, so this must be revisited
  before avatars are built on these rules.
- **No virus scanning.** There is no free server-side scanner worth the name.
  An archive is the one type whose contents cannot be validated at all, which
  is the honest argument against accepting RAR and ZIP — recorded here rather
  than solved.
- **No inline image previews.** Rendering one means fetching every image in a
  thread to draw the page. A file nobody opened should cost nothing to scroll
  past.
- **No separate attachment list per thread.** Files are findable where they
  were said, like everything else in a conversation.
