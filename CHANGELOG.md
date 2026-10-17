# Changelog

## 1.0.0 (2026-10-16)

First release.

- Raw trip-leg observations → pre-computed averages by origin, destination, vehicle type,
  day of week (optional) and shift, over a half-open D-1…D-180 window in
  `America/Sao_Paulo`, with today excluded.
- Two designs producing the same aggregate: **simple** (default; `$group` over the whole
  window + `$out`) and **incremental** (buckets by shift or by hour, k days plus late days
  detected by an `ingestedAt` watermark, `$merge` with `whenMatched: "replace"`).
- ETA fallback in one indexed `find` (≤ 21 documents) with a level hierarchy
  (`dow+shift` → `shift` → `overall` → `no_history`); the key is derived from the config
  version that produced the aggregate.
- Job with a lease lock, retry with backoff, coverage tracking per bucket grain and full
  rebuild when the stored grain/config changes; everything recorded in `job_runs`.
- `$jsonSchema` validators on every collection, idempotent bootstrap, TTL retention,
  deterministic sums (rounded to 6 decimals).
- FastAPI + Vite/React UI in the portfolio "Dark Stage v4" layout: ETA query, raw vs
  materialized with real `explain`, simple × incremental comparison, job and moving window,
  configuration and under-the-hood views.
- Runs on MongoDB Atlas (tested on 9.0.4) or a local MongoDB 8.0 in Docker, selected from
  `.env`. 109 tests on both, a client-perspective resilience battery, a real chaos script
  and an `escala` benchmark (1.86 M observations).
