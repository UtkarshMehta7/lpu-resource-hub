# Expertise search: measured latency

The specification asks that expertise search *"returns relevant researchers
across departments in under 1 second"*. That is a claim about latency, so it
is measured rather than asserted.

Reproduce with:

```bash
cd backend
TEST_DATABASE_URL=... python scripts/benchmark_search.py --records 25000 --repeats 30
python scripts/benchmark_search.py --cleanup     # removes every row it made
```

## What is being measured

**Latency = request received → response returned.** The benchmark drives the
search through the ASGI application, so each sample includes routing,
authentication, authorisation, the SQL, tag loading and JSON serialisation.

Timing the SQL alone would flatter the result by omitting most of what a
person actually waits for.

## Environment

| | |
|---|---|
| Hardware | Apple Silicon laptop, PostgreSQL 18 running locally |
| Database | The project's test database, migrated to head |
| Directory size | **25,000 researcher profiles** (also run at 5,000) |
| Per profile | 3 skills, 2 research areas, a bio, a department |
| Departments | 8 |
| Samples | 30 per query, after one warm-up request |
| Client | `fastapi.testclient.TestClient` against the real application |

This is a **local** measurement. The deployed instance is a free Render
container against Neon, which will be slower — the headroom below is what
makes that acceptable, not an argument that the two are equivalent.

## Results — 25,000 researchers

| Query | Hits | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| single common term | 20 | 75.6 ms | 78.4 ms | 78.7 ms | 78.7 ms |
| multi-word phrase | 20 | 92.1 ms | **113.5 ms** | 191.3 ms | 191.3 ms |
| cross-department, broad | 20 | 80.9 ms | 84.0 ms | 85.4 ms | 85.4 ms |
| rare term | 20 | 83.4 ms | 87.0 ms | 87.8 ms | 87.8 ms |
| two terms, few hits | 0 | 92.9 ms | 94.3 ms | 94.4 ms | 94.4 ms |
| filtered by skill | 20 | 64.1 ms | 68.7 ms | 69.3 ms | 69.3 ms |
| deep pagination (page 5) | 20 | 76.7 ms | 78.3 ms | 78.9 ms | 78.9 ms |
| no query, first page | 20 | 40.9 ms | 43.2 ms | 43.5 ms | 43.5 ms |
| registration-number prefix | 10 | 78.9 ms | 80.4 ms | 85.8 ms | 85.8 ms |

```
SEARCH
Dataset size:        25,000 researcher profiles
Benchmark queries:   9
Samples per query:   30
Worst p50:           92.9 ms
Worst p95:           113.5 ms
Worst p99:           191.3 ms
Acceptance target:   < 1000 ms (p95)
Status:              PASS  (≈9x headroom)
```

At 5,000 profiles the worst p95 was **46.7 ms**. Five times the data cost
roughly 2.4× the latency — sub-linear, because the bounded `LIMIT` dominates.

## Query plans

The filter alone uses the GIN index:

```
Bitmap Index Scan on ix_researcher_profiles_search_document
```

The full search — filter, join to `users`, `ts_rank` ordering — chooses a
**parallel sequential scan** instead:

```
Limit  (actual time=10.162..11.283 rows=20)
  ->  Nested Loop
        ->  Gather Merge  (workers launched: 1)
              ->  Sort  Sort Key: ts_rank(...) DESC
                    ->  Parallel Seq Scan on researcher_profiles
                          Filter: search_document @@ websearch_to_tsquery(...)
                          Rows Removed by Filter: 11160
        ->  Index Only Scan using pk_users on users
Execution Time: ~11 ms
```

That is the planner being **right**, not a missing index. Ranking needs the
tsvector itself, so the rows must be fetched from the heap regardless; when a
term matches ~11% of the table, scanning in parallel beats an index lookup
followed by 2,700 heap fetches. The index remains valuable for selective
terms, and a `Rows Removed by Filter` line is not evidence of a problem when
execution is 11 ms.

**No index was added or changed for this benchmark.** The existing GIN index
on `search_document` (migration 0005) and trigram index on `users.full_name`
were sufficient, and nothing was optimised to reach the target.

## Honest limitations

- **Synthetic term distribution.** Skills and areas are rotated evenly across
  profiles, so *every* term matches about 10.7% of the directory. Real
  directories are skewed — a few very common specialisms and a long tail — and
  a skewed corpus would favour the index more than this one does. The
  benchmark is therefore closer to a worst case for index usage than a best
  one.
- **Local hardware, not production.** See the environment note above.
- **The search rate limiter is replaced during the run.** The endpoint allows
  60 requests a minute per IP; a benchmark fires hundreds. Without this, every
  sample after the first minute measures how quickly the limiter says no,
  which looks like a very fast search and means nothing. The first version of
  this benchmark had exactly that bug — most rows were timing a `429`.
- **Single client, no contention.** These are latency figures, not a
  throughput or concurrency test.
- **Names are synthetic**, drawn from a small fixed list, so trigram matching
  on `full_name` sees less variety than it would in practice.

## Guarding against regression

`backend/tests/test_search_performance.py` runs in CI but deliberately makes
**no wall-clock assertion** — a shared runner's timing varies with whatever
else is on the box, so a latency threshold there is a flaky test, not a
performance guarantee.

It asserts the properties that actually decay and are stable to observe:

- the GIN index exists and is a GIN index
- the plan contains no `SubPlan` — that is, search has not become a query per
  result
- ranking stays a bounded top-N rather than a full sort
- search really does reach across departments
- paging neither repeats nor loses a researcher

The wall-clock numbers come from the benchmark script, run deliberately and
recorded here.
