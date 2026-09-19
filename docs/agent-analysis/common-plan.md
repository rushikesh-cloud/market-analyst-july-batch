# Common foundation implementation plan

Progress: [task status tracker](status.md#common-foundation). Complete C01–C10 before starting an agent track. No fundamental, Yahoo, or Tavily business logic belongs in these tasks.

Read [execution and validation conventions](README.md) and [the master plan](../../plan.md). Agent tracks inherit the interfaces below and do not reimplement them.

## Foundation contract

- Shared package: `backend/app/analysis/`; agent implementations live in dedicated subpackages. A registry maps `fundamental`, `technical`, and `news` to adapters exposing `run(context) -> AgentResult`.
- `AnalysisContext`: run ID, company ID/name/canonical ticker snapshot, UTC assessment timestamp fixed at first execution, effective model configuration, provider dependencies, artifact/evidence store, and shared budget/deadline. User/model tool arguments cannot override company identity.
- `AgentResult`: schema version, agent type, company snapshot, assessment/evidence dates, horizon, summary, parameters, nullable final score, confidence (`low`, `medium`, `high`), coverage percentage, strengths, risks, limitations, evidence references, and agent-specific structured details.
- `ParameterScore`: stable key, display name, configured weight, nullable score, explanation, and evidence IDs. Fixed-dimension keys/weights are server-owned. News event weights are calculated by code from validated event classifications; the model cannot submit the final weight or arithmetic.
- Evidence has immutable run-local IDs, type, original source metadata, a bounded supporting excerpt or data observation, and provenance. Chunk and article citations reference this ledger; chart/data artifacts reference registered artifact IDs.
- Terminal result status is `completed` or `insufficient_data`. Provider/runtime failures use run status `failed` with a safe error code/message, not a manufactured research result.
- An agent returns a validated typed result; it does not own API routes, queue commits, lease management, or frontend polling.

## C01 — Typed contracts, fixtures, and registry

**Status:** [See tracker](status.md#common-foundation). **Depends on:** none.

**Implementation**

- Define shared Pydantic contracts, explicit agent-detail variants, state/error enums, and a registry supporting injected test adapters.
- Define separate model-output and persisted-result schemas: identity, weights, timestamps, coverage, and final arithmetic are server-owned.
- Add representative successful, insufficient-data, failed-run, and partially covered fixtures for all three agents. Fixtures are synthetic and do not claim real financial facts.
- Preserve required fields while allowing nullable findings; use ISO timestamps with timezone and reject non-finite numeric values.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C01-01 | U | Round-trip all three detail variants through JSON: types, evidence references, nulls, and timestamps survive without field loss. |
| C01-02 | U | Submit scores -0.1, 10.1, NaN, infinity, booleans, or strings: validation rejects them; numeric 0 and 10 pass. |
| C01-03 | U | Supply the wrong detail variant, duplicate parameter keys, missing required metadata, or unexpected fields: validation identifies the invalid contract. |
| C01-04 | U | Attempt to inject another company, agent type, parameter weight, or assessment date through model output: rejected or absent from the allowed output schema; server values remain authoritative. |
| C01-05 | U | A parameter cites an unknown evidence ID: finalization rejects it; known run-local IDs pass. |
| C01-06 | U | Registry receives an unknown agent or an uninstalled implementation: return a typed unavailable/invalid-agent outcome; no fallback to a different agent. |

**Done when:** all fixtures validate, invalid cases fail, and each agent's required details can be represented without changing shared identity or lifecycle rules.

## C02 — Deterministic scoring and evidence coverage

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01.

**Implementation**

- For fixed-dimension agents, compute coverage as `100 * supported_weight / total_weight` and final score as `sum(score * weight) / supported_weight`, rounded once to one decimal with decimal half-up rounding.
- Require at least 70% unrounded coverage and each agent's mandatory evidence gates. Missing scores remain null; do not insert zero or five.
- Expose a generic normalized weighted-average utility for news events. News defines its own evidence denominator in news/N05 and does not use absent news categories as missing parameters.
- Validate finite nonnegative weights, unique keys, nonzero denominator, and evidence-backed eligibility before aggregation. Do not round components before aggregation.
- Confidence describes evidence, not direction: high requires complete required coverage, consistent sources, and no material freshness/ambiguity flags; medium is sufficient but limited; low is sparse, materially conflicted, or stale. Domain gates may lower it, never raise it above the shared evidence assessment.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C02-01 | U | Technical scores 8/6/4/7 with weights 30/25/25/20: result 6.3 and coverage 100%. |
| C02-02 | U | Missing technical volume leaves scores 8/6/4 and weight 80: result 6.1, coverage 80%, missing volume remains null. |
| C02-03 | U | Coverage is exactly 70%, just below 70%, and zero: only the first is eligible if required gates pass; no division by zero. |
| C02-04 | U | Coverage exceeds 70% but a mandatory evidence gate fails: final score is null and result is insufficient data. |
| C02-05 | U | All valid scores are 0 or all are 10, weights arrive out of order, or a score rounds at x.x5: correct bounded result, stable order-independent arithmetic, half-up rounding. |
| C02-06 | U | Negative/non-finite weights, duplicate keys, an empty input, or an unsupported cited score: no final number is emitted. |
| C02-07 | U | Same scores with stale/conflicting evidence: numerical direction is unchanged, confidence is reduced and limitations explain why. |

**Done when:** both agent families can reuse tested arithmetic while retaining their explicitly different coverage rules.

## C03 — LangChain models, configuration, and provider boundaries

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01.

**Implementation**

- Resolve and lock compatible `langchain` and `langchain-openai` versions for Python 3.13. Revalidate the existing `openai<2` constraint against the selected versions and update it when required; regression-test existing embedding calls.
- Extend the resource layer with lazy Azure chat-model factories using the existing endpoint, API version, Key Vault credentials, and configured Terra deployment by default.
- Add optional `ANALYSIS_FUNDAMENTAL_DEPLOYMENT`, `ANALYSIS_TECHNICAL_DEPLOYMENT`, and `ANALYSIS_NEWS_DEPLOYMENT` overrides, plus optional `TAVILY_API_KEY_SECRET`. A missing Tavily setting must not break unrelated agents or app startup.
- Use `create_agent` and explicit `ToolStrategy` structured output. Limit schema-repair attempts to two and include them in the model-call budget.
- Disable hidden provider retries where the shared retry policy owns them. Retry transient timeouts/429/5xx at most twice with bounded backoff; do not retry credentials or unsupported-capability errors.
- Define typed failures for configuration, provider unavailability, unsupported image input, invalid output, and budget exhaustion. Redact raw provider errors and secrets from APIs/logs.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C03-01 | U | Default and per-agent override configurations: selected deployment is correct and other agents are unaffected. |
| C03-02 | U | Import/start app with no Tavily secret setting: no Tavily lookup occurs; requesting news configuration reports a safe configuration error. |
| C03-03 | U | Inject a fake tool-calling model into an actual `create_agent` graph: tool execution and validated `structured_response` work without a live API. |
| C03-04 | U | Invalid structured response becomes valid on repair, or remains invalid after two repairs: bounded success or typed failure, never an unlimited loop. |
| C03-05 | U | Transient failure then success, repeated transient failures, auth failure: expected retry counts, deadline-aware backoff, no duplicate SDK retry layer. |
| C03-06 | U | Provider exception includes a sentinel secret/URL: neither API error nor captured logs contain it. |
| C03-07 | U | Run existing resource and embedding/search tests with the locked dependencies: no client-construction or embedding-shape regression. |
| C03-08 | L | Configured text model calls one tool and returns the schema; configured technical model identifies a distinctive labeled test image: record capability results; unsupported vision blocks technical readiness only. |

**Done when:** dependency resolution and offline cases pass; live capability results are recorded and required deployments are verified before C10 completion.

## C04 — NSE ticker normalization and compatibility

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01.

**Implementation**

- Normalize new/edited input by trimming and uppercasing; append `.NS` to a bare equity symbol. Accept letters/digits and internal `&`/`-` as used by NSE equities; reject whitespace, indices, FX syntax, duplicate suffixes, and explicit non-NS exchange suffixes.
- Check length after normalization and uniqueness on the canonical value. Compare against canonicalizable legacy bare symbols so creating `RELIANCE.NS` cannot duplicate legacy `RELIANCE`.
- Separate permissive legacy output serialization from strict create/update validation so existing incompatible records remain readable/editable.
- Do not infer an exchange for existing bare symbols during analysis. Existing noncanonical records require explicit correction/save before analysis. Detect canonical collisions without merging companies or their documents.
- Update company form examples/errors and `design.md` to the NSE-only contract. Syntax validation does not assert that Yahoo recognizes the company.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C04-01 | U/A | ` reliance `, `reliance.ns`, `M&M`, and `BAJAJ-AUTO.NS`: canonical `.NS` output; applying normalization twice changes nothing. |
| C04-02 | U/A | `RELIANCE.BO`, `7203.T`, `^NSEI`, `EURUSD=X`, `.NS`, `ABC.NS.NS`, embedded spaces, or excessive canonical length: clear validation error. |
| C04-03 | A/P | Create/update two spellings of the same symbol, including a canonicalizable legacy bare record: conflict; original names, IDs, and documents remain unchanged. |
| C04-04 | A | List old global/bare symbols: API still serializes them; analysis rejects them with a correction action until explicitly saved with valid input. |
| C04-05 | A | Two legacy records would normalize to one symbol: editing reports conflict rather than deleting/merging either record. |
| C04-06 | B | Add/edit shows canonical ticker after save; invalid input preserves the form and exposes an accessible inline error. |

**Done when:** canonical input works, legacy output remains readable, and normalization does not silently relabel existing companies.

## C05 — Analysis persistence and migrations

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01.

**Implementation**

- Add the next versioned migration for analysis runs, terminal result JSON, evidence snapshots, and registered artifact metadata. Reuse existing SQLAlchemy/migration conventions.
- Store company FK and immutable snapshot, agent type, status, timestamps, attempts, lease owner/generation/expiry, progress, safe errors, schema/prompt/scoring/model versions, usage metadata, and persisted execution-budget counters.
- Enforce one active (`queued`/`running`) run per company/agent using a PostgreSQL partial unique index. Terminal history is append-only from the application; reruns get new IDs.
- Historical evidence must not cascade-delete when an original document is removed. Block company deletion while analysis history exists.
- Preserve SQLite company CRUD; analysis endpoints explicitly require PostgreSQL. Do not make SQLite pretend to validate PostgreSQL locking behavior.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C05-01 | P | Apply migration to an existing database and rerun the migrator: tables/indexes appear once, existing companies/documents/chunks remain intact. |
| C05-02 | P | Two connections insert active runs for the same company/agent: exactly one persists; different agents/companies can each queue work. |
| C05-03 | P | Finish a run and create a rerun: distinct IDs, original result unchanged, new active row accepted. |
| C05-04 | P | Delete an original source document after completion: saved citations/excerpts and result remain readable; company deletion with history is blocked. |
| C05-05 | P | Persist then reconnect and deserialize success/insufficient/error states: no loss of identity, version, null-score, evidence, or timestamp fields. |
| C05-06 | U/A | Start with SQLite: existing company operations work; analysis calls return an explicit PostgreSQL-required error. |

**Done when:** real PostgreSQL enforces the invariants and migrations preserve existing data.

## C06 — Evidence ledger and artifact storage

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01, C05.

**Implementation**

- Implement run-scoped evidence IDs with immutable source metadata and excerpts. Repeated identical evidence in one run is deduplicated; evidence in different runs stays independent.
- Store files under a git-ignored `analysis-artifacts/<run-id>/` workspace directory, using server-generated IDs and relative paths. Register MIME type, size, content hash, and purpose.
- Write artifacts atomically before registering availability. Attempt-specific paths prevent a stale worker from replacing another attempt's file.
- Serve only registered artifacts belonging to the requested run. Reject traversal/symlink escape and mismatched run IDs; do not expose paths or provider credentials.
- Retain completed artifacts for history. Document persistent-volume requirements without building or deploying Docker.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C06-01 | U/P | Register/read evidence and a PNG, restart the service: metadata, bytes, hash, and MIME type agree. |
| C06-02 | U/A | Request another run's artifact ID, `../` path, absolute path, encoded traversal, or escaping symlink: no file outside the run registry is returned. |
| C06-03 | U/P | Interrupt writing or fail registration: partial content is never served as an available artifact. |
| C06-04 | U/P | Same evidence appears twice in one run and in a second run: one local entry in the first run, independent provenance in the second. |
| C06-05 | U/A | Registered file is missing or hash differs: explicit unavailable/corrupt artifact outcome; other run results remain accessible. |
| C06-06 | P | An expired worker writes an artifact after lease transfer: it cannot replace or publish the active attempt's artifact. |

**Done when:** artifacts and evidence are durable, isolated, and reviewable without depending on mutable source records.

## C07 — Analysis API and history

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C04–C06.

**Implementation**

- Add master-plan endpoints for starting a run, listing company history, reading a run, and fetching artifacts. POST accepts only `agent_type`; server resolves identity and defaults.
- Return 202 for a new or already-active run, 404 for missing company/run/artifact, 422 for invalid payload, 409 for a ticker requiring correction, and 503 for unavailable analysis configuration/backend/adapter.
- Handle active-run insertion races by returning the existing run. No LLM/provider request executes in the HTTP submission path.
- History uses `limit` (default 20, maximum 100), `offset` (default 0), optional agent filter, and stable descending creation-time/ID ordering.
- Return safe progress, result, and error details; omit raw prompts, provider exceptions, secret settings, and absolute file paths.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C07-01 | A/P | Submit a valid run: 202 and persisted queued ID; injected provider is not called by the endpoint. |
| C07-02 | A/P | Repeat submission concurrently while active, then after completion: same active ID, then a new ID; at most one active row. |
| C07-03 | A | Unknown IDs, invalid agent, extra identity fields, invalid pagination, bad legacy ticker, uninstalled adapter, and SQLite backend: documented status/error code for each. |
| C07-04 | A/P | Page/filter histories with tied timestamps across multiple companies: stable ordering, no repeated/missing entries under a fixed dataset, no cross-company results. |
| C07-05 | A | Read queued/running/completed/insufficient/failed fixtures: schema and nullable result fields match the lifecycle. |
| C07-06 | A | Fetch valid and mismatched artifacts: correct bytes/content type or safe 404; no filesystem path disclosure. |

**Done when:** client-visible contracts are stable and the API remains responsive without a running analysis worker.

## C08 — Durable worker, execution limits, and recovery

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C02–C03, C05–C07.

**Implementation**

- Add a separate analysis worker and `npm run worker:analysis`; claim jobs with row locks and skip-locked semantics, never from ingestion tables.
- Use 60-second leases with a heartbeat every 15 seconds, at most three claimed attempts, and a five-minute deadline measured from first execution across attempts. Freeze `as_of` then and preserve it on recovery.
- Check owner and lease generation on progress/evidence publication/terminal writes. Stop accepting work after lease loss; a stale process cannot overwrite state.
- Enforce provider timeout of at most 45 seconds or remaining deadline, whichever is shorter; two transient retries; ten model invocations including schema repairs. Domain tools also enforce their own smaller caps. Heartbeats must continue while a provider call is in flight.
- Do not rely solely on a graph recursion limit: enforce call counts and time budgets at tool/model boundaries and persist consumed budget before external calls so recovery does not reset limits. Stop network/tool work at the deadline; run the agent in an isolated execution process that the supervising worker can terminate, while the supervisor owns heartbeats and final state writes.
- On process interruption, reclaim an expired run within the remaining deadline and attempt budget. Deadline/attempt exhaustion ends `failed`; recoverable resource caps may yield a valid partial result only if normal evidence gates pass. A deliberate insufficient-evidence conclusion is `insufficient_data`.
- Persist stage labels, durations, usage, and tool-call metadata without storing hidden reasoning or raw credentials. Close database transactions before slow provider calls.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C08-01 | P | Two worker connections race for queued work: each run is claimed by one owner; work for other companies remains claimable. |
| C08-02 | P | Owner dies, lease expires, new owner finishes, old owner returns: one terminal result from the new generation; old progress/result writes fail. |
| C08-03 | U/P | Fake clock advances during a slow model call: heartbeats renew; at deadline execution stops and cannot publish a later result. |
| C08-04 | U/P | Three failed claims/recoveries or five-minute deadline expires: terminal failure, no fourth attempt, frozen assessment time unchanged. |
| C08-05 | U | Tool/model/repair/retry limits are exhausted independently: bounded call counts, no hidden retry amplification, correct safe failure or valid partial result. |
| C08-06 | P | Process dies before completion and after committing completion: first is recoverable; second is never rerun or overwritten. |
| C08-07 | P | Analysis worker runs beside ingestion worker: each claims only its own tables; a long provider call holds no database transaction blocking unrelated writes. |
| C08-08 | U/P | Invalid result, unknown citations, provider outage, and genuine missing evidence: failure vs insufficient-data classification is correct; no fabricated score. |

**Done when:** competing-connection and interruption tests pass with real PostgreSQL, bounded calls, and no stale-owner publication.

## C09 — Shared analysis UI and browser-test harness

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01, C04, C07.

**Implementation**

- Add a focused analysis page and shared API/types/status/history/result-summary components. Mount them from the existing app shell instead of growing unrelated company/document components.
- Company selector, three accessible tabs, one primary run action for the selected agent, status/progress, history, generic parameter table, confidence/coverage/limitations, and recovery actions use existing design tokens.
- Use fixtures for all agents until their adapters/renderers are installed. Production must show unavailable agents honestly; never register fixture adapters in production.
- Poll active selected runs every two seconds, stop on terminal state/unmount, ignore obsolete responses, and fetch history on refresh/reselection. Keep a previous successful result visible while a rerun progresses.
- Add Playwright as a frontend development test dependency and `npm --prefix frontend run test:e2e`; mock API routes for deterministic UI cases. Update `design.md` for the analysis page contract.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C09-01 | B | Empty company list, initial selection, and no history: clear empty states and correct enabled/disabled run action. |
| C09-02 | B | Start a run, double-click, observe progress and completion: one active run, correct status, polling stops on terminal state. |
| C09-03 | B | Switch company/tab while a slower response returns: old result never replaces the newly selected company's view. |
| C09-04 | B | Reload during a run, select history, and rerun: active state resumes from server, history persists, previous success remains visible. |
| C09-05 | B | Insufficient data, invalid ticker, API read failure, and unavailable agent: meaningful recovery action, preserved context, no fake 0/5 score. |
| C09-06 | B | Complete keyboard navigation, screen-reader status announcements, mobile width, and 200% zoom: labels/focus/table access remain usable. |
| C09-07 | B | Render text containing HTML/script-like content from evidence/errors: it displays safely and cannot execute code. |

**Done when:** fixture-driven browser tests and frontend build pass; agent tracks can add their detail renderer without reimplementing selection/history/polling.

## C10 — Foundation acceptance and handoff

**Status:** [See tracker](status.md#common-foundation). **Depends on:** C01–C09.

**Implementation**

- Exercise a fixture adapter through API → PostgreSQL queue → worker → evidence/result/artifact → browser using the real shared execution path.
- Document isolated PostgreSQL tests, explicit live flags, environment variables, startup commands, and frozen contract versions. Production registry excludes fixtures.
- Run the regression suite and collect coverage for new shared modules; map all Cxx test IDs to implementations.
- Record a foundation commit that all three agent plans can start from. Missing live model/vision verification leaves this gate blocked for release readiness, with the precise missing configuration recorded.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| C10-01 | P/B | Submit a fixture run from the UI and complete it with the worker: status, score, citations, and artifact survive reload. |
| C10-02 | P/B | Fixture returns insufficient data or raises provider failure: distinct correct recovery states; failed run does not erase previous success. |
| C10-03 | U/P/B | Run all common task cases, existing backend regressions, and frontend build: required suites pass and coverage targets are met. |
| C10-04 | U/A | Run production configuration with fixture adapters absent: unimplemented agents are explicitly unavailable, not simulated as completed. |
| C10-05 | L | Verify configured Azure tool calling/structured output/vision and save redacted observations: all model requirements for downstream tracks are proven. |
| C10-06 | P/B | Start without analysis worker, then start it: queued run remains durable and completes; UI accurately showed queued while the worker was absent. |

**Done when:** the common foundation is committed, validated, and documented. Fundamental, technical, and news work can now proceed independently using their own providers, evidence rules, and UI detail components.

## C01 handoff

- Implementation commit: this commit (resolve through Git history).
- Interfaces: `analysis/contracts.py`, `registry.py`, and `fixtures.py`; immutable
  runtime identity, separate model schemas, three detail variants, safe failures,
  explicit registry, and 12 synthetic fixtures. No production adapters installed.
- Tests: `tests/test_analysis_contracts.py` maps C01-01–C01-06 to seven methods,
  including safe errors. Focused unittest suite: 7 passed; statement and branch
  coverage for contracts, fixtures, registry: 100%.
- Command: `uv --directory backend run coverage run --branch --source=app.analysis
  -m unittest tests.test_analysis_contracts` followed by `coverage report -m`.
- Live checks: not applicable. Baseline backend: 48 tests, 6 expected PostgreSQL
  skips. Baseline frontend build passed (existing bundle-size advisory).
- Publication contract: C06/C08 must compare evidence snapshots against persisted
  ledger contents as well as validating registered IDs and company/run identity.
- Next: C02/C03/C04/C05 are independent and are now assigned concurrently.
- Shared guidance used: `/home/azureuser/projects/knowledgebase/01-Active-Standards/retrieval-and-precedence.md`;
  implementation follows the current project task pack.

## C02 handoff

- Implementation commit: this commit.
- `analysis/scoring.py` exposes fixed server-owned dimensions, normalized weighted
  averages, confidence assessment, and explicit mandatory evidence gates.
- C02-01–C02-07 map to seven methods in `tests/test_analysis_scoring.py`: all pass,
  no skips. Coverage: 107 statements and 46 branches, 100%.
- Command: `uv --directory backend run coverage run --branch
  --data-file=/tmp/analysis-c02.coverage --source=app.analysis.scoring
  -m unittest discover -s tests -p test_analysis_scoring.py`.
- Decimal half-up rounding occurs once; eligibility uses unrounded coverage.
  News retains responsibility for its event denominator. No live checks apply.
- Next: C08 consumes this arithmetic after its remaining dependencies pass.
