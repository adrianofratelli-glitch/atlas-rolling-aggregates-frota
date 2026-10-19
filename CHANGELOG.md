# Changelog

## 2.1.0 (2026-10-19)

- **One "Consultar" step** replaces "Query scenarios", "Outside the base" and "Few samples":
  the UI goes from 7 to 5 steps (raw and schema, the rule, build the base, query, when it
  refreshes). Old `#passo=6`/`#passo=7` links fall back to step 1.
- The query form has origin and destination as separate selects (only valid destinations
  for the origin), vehicle type, **vehicle** ("all vehicles of the type" or one of 15) and
  the period (default window, specific dates, last N days). The default window for a whole
  type answers automatically from the ready base; anything else waits for "Calcular".
- **A specific vehicle always goes to the raw**, even in the default window: the base is
  per vehicle type, never per vehicle. `veiculoId` is validated (`VEI-<TYPE>-<n>`, must
  exist for that type; 422 otherwise), enters the saved-result key and the first `$match`
  (same compound index, no new index). Default window + vehicle is relative: the saved
  result expires at the next job.
- "guardar o resultado" is **ticked by default** in the UI (the API `persistir` field stays
  explicit); validity 1–30 days for specific dates, "until the next job" for relative
  periods.
- `/api/opcoes` returns `veiculos` per type, read from the raw (natural order, cached until
  the next reset).
- Generator: 15 vehicles per type in the demo profile (3 in the test profile); same volume
  and same sampled times, only the distribution among vehicles changed.
- `$merge` explanation shortened to "Grava o resultado numa collection persistente."; step 3
  shows that sentence plus the "materialized view" label.
- New exported pipeline `docs/pipelines/cenario-raw-veiculo.*`.
- 103 tests on Atlas (9.0.4) and local MongoDB 8.0.34.

## 2.0.0 (2026-10-19)

**Breaking: new API and new schema.** The v1 routes (`/api/eta`, `/api/comparar`,
`/api/comparar-modos`, `/api/config`, `/api/avancar`, `/api/atrasado`, `/api/buckets`,
`/api/capo`…) and collections (`trecho_media_historica`, `trecho_bucket_*`, `config`,
`config_versoes`, `ingestao_pendente`, `job_locks`, `veiculos`, `tipos_veiculo`) are gone.
Recreate the database with `make seed` (or "Resetar demo").

- One-page UI with a guided 7-step script (raw and schema, the rule, build the base, query
  scenarios, outside the base, when it refreshes, few samples) and a
  "Ver query / chamada executada" drawer on every step that runs something.
- The materialized base is now `trecho_media_dow_hora`: origin × destination × vehicle
  type × ISO day of week (`$isoDayOfWeek`, 1 = Monday) × hour, built daily with `$merge`
  replace. Any combination of days and hour range is a sum of ready documents; mean and
  standard deviation from count, sum and sum of squares.
- Other periods (specific dates, last N days) are computed on the raw collection, with
  optional persistence in `consultas_salvas` (TTL; 1–30 days or until the next job).
- Widening when there are fewer than 5 samples, labelled as a rule to validate.
- `dataRef` (reference date) replaces the simulated `asOf`: the seed generates data around
  the real date; "Resetar demo" rebuilds it around the click and queues 14 days of
  simulated arrivals in `ingestao_simulada`.
- Job cleanup by the server clock (`hello.localTime`): overlapping runs never delete each
  other's output; no lease.
- Atlas Scheduled Triggers (daily job at 03:10 São Paulo, hourly simulated ingestion) in
  `atlas-trigger/`, generated from the Python pipelines and tested in Node. Not deployed
  in the demo.
- Removed: incremental design, buckets, watermark, versioned config, night rule, simulated
  clock, raw-vs-materialized `explain` tab, benchmark profile `escala`.
- The data model is presented as a reference model to adapt to the real master data.
- Final review: on-demand `docsLidos` counts the raw docs matched by the first `$match`; the UI labels the time as "ida e volta ao banco"; an absolute period ending today expires at the next job; partially-out-of-retention periods warn; `/api/estado` `ultimoJob` is the latest ok run (`ultimoErro` apart); the step 6 preview is cached in-process.
- 96 tests on Atlas (9.0.4) and local MongoDB 8.0.34.

## 1.0.1 (2026-10-16)

- The API no longer exposes the job owner (`host:pid`) and masks server `host:port` in driver error messages (`job_runs`, `/api/estado`, 503 details). Found while recording the offline replica: a real `AutoReconnect` on Atlas carried the cluster hostname.
- Inline portfolio favicon: the UI no longer requests `/favicon.ico` (a console 404 in the offline player).
- Packaged in the PoV Demo Player 0.7.0 as `rolling`.

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
