# Agent implementation task pack

Track implementation progress in the **[task status tracker](status.md)**. These documents specify work and tests; completion is recorded only after each task passes its gate.

## Execution order

1. Complete [Common foundation](common-plan.md), C01–C10, and record the foundation commit.
2. Implement [Fundamental](fundamental-plan.md), [Technical](technical-plan.md), and [News](news-plan.md) independently against that foundation. Each track includes its own UI integration and acceptance tests.
3. Complete the cross-agent acceptance task I01 below.

The product scope and defaults come from [the master plan](../../plan.md). These detailed plans define implementation and validation details. In particular, scores use normalized weighted averages, news coverage uses retained event weights rather than absent news categories, and existing ambiguous tickers are not silently migrated.

| Workstream | Task IDs | Completion gate | Progress |
|---|---|---|---|
| Common foundation | C01–C10 | Shared runtime, API, contracts, and fixture-backed UI pass C10 | [Tracker](status.md#common-foundation) |
| Fundamental | F01–F07 | Latest-report, sector-aware analysis passes F07 | [Tracker](status.md#fundamental-agent) |
| Technical | T01–T07 | Yahoo data, chart, and vision analysis pass T07 | [Tracker](status.md#technical-agent) |
| News | N01–N07 | Tavily evidence and event scoring pass N07 | [Tracker](status.md#news-agent) |
| Integration | I01 | All three real adapters pass together | [Tracker](status.md#cross-agent-integration) |

### Mapping from the master plan

| Original milestone | Detailed tasks |
|---|---|
| S01: contracts and task pack | This task pack; C01–C02 |
| S02: LangChain and models | C03 |
| S03: NSE company contract | C04 |
| S04: durable analysis execution | C05–C08 |
| F01–F02: fundamental implementation | Fundamental F01–F07 |
| T01–T03: technical implementation | Technical T01–T07 |
| N01–N02: news implementation | News N01–N07 |
| U01: analysis UI | C09 plus each track's task 06 |
| V01: integrated validation | C10, each track's task 07, I01 |

Detailed IDs are qualified by their document, for example `technical/T03`, to distinguish them from the original coarse milestones.

## Rules for every implementation session

- Read repository instructions, the master plan, this index, the [task status tracker](status.md), and the selected task's plan. Read `design.md` before changing UI.
- Start one task whose dependencies are complete. Keep modules focused; use `backend/app/analysis/` for shared infrastructure and its `fundamental/`, `technical/`, and `news/` subpackages for agent-specific code.
- Use the existing resource layer, migration ordering, API patterns, and component/CSS conventions. Do not create competing provider clients, job queues, or result formats in an agent track.
- Implement and run the task's named tests. Never substitute live model output for deterministic calculation or persistence tests.
- Update the task row and summary in [the status tracker](status.md) when starting, blocking, or completing work, and append the handoff record below to the relevant plan. Commit that task's intended changes after validation, preserving unrelated work. Do not build Docker.
- If an assumption proves false, record the evidence and amend the affected contract and tests before dependent work begins.

### Handoff record template

```text
Task ID / status: pending | in_progress | complete | blocked
Implementation commit:
Files and public interfaces changed:
Test IDs mapped to test methods or browser scenarios:
Commands run and pass/fail/skip counts:
Coverage report for changed modules:
Live checks: passed | failed | not run (reason)
Artifacts or redacted observations:
Limitations / blockers:
Next task and prerequisites:
```

## Validation conventions

- **U:** deterministic unit tests using `unittest`, explicit fixtures, fake clocks, and injected providers.
- **A:** FastAPI contract tests using `TestClient` and the real validation/serialization path.
- **P:** actual PostgreSQL tests for SQL, pgvector, migrations, locks, and competing connections. Stub external providers only. Use isolated schemas; concurrency tests need independent transactions and schema cleanup rather than one shared rollback transaction.
- **B:** Playwright browser tests against mocked HTTP fixtures for UI behavior, plus integrated API-backed scenarios at release acceptance.
- **L:** explicitly enabled live-provider smoke/evaluation checks. Default automated tests must not spend provider credits or access production documents.

Each test table states a stimulus and an observable expected result. Map its stable test IDs to actual test methods in the task handoff. Every listed case is required; parameterize equivalent cases where appropriate.

For new deterministic domain/services/worker code, target at least 90% statement and 85% branch coverage, measured over the new modules, with no uncovered company-isolation, scoring-denominator, terminal-state, or lease-ownership branches. A coverage percentage does not replace the listed scenarios. Exclude third-party code and generated files, not difficult application branches. Browser and live-model quality checks are reported separately.

Reuse the existing backend commands:

```bash
uv --directory backend run python -m unittest discover -s tests -v
uv --directory backend run coverage run --branch -m unittest discover -s tests
uv --directory backend run coverage report -m
npm run build
```

C09 introduces the frontend browser-test command; C10 documents the isolated PostgreSQL and live-test commands with their environment flags. Run focused task tests while working and the complete relevant regression suites at each workstream gate. Missing provider credentials are an explicit live-check blocker, never a silent pass.

### Live evaluation standard

- Use approved test companies/documents and record the run date, source snapshot IDs, model deployment, and prompt/scoring versions.
- Run the representative fixture scenarios three times at the final track gate; automated assertions cover schema, scope, citations, numerical consistency, and termination on every run.
- Review narrative claims against the cited evidence. Live sentiment or health scores need not be byte-identical; record their range and investigate contradictory conclusions under identical evidence.
- A track's live acceptance fails for fabricated material facts, wrong-company evidence, unsupported final scores, or a text-only substitute for required chart vision. Do not mark its release gate complete until those failures are resolved.

## I01 — Cross-agent application acceptance

**Status:** [See tracker](status.md#cross-agent-integration). **Depends on:** C10, fundamental/F07, technical/T07, news/N07.

**Deliverable:** verify all three production adapters in the same application, finalize operating instructions, and record a release-readiness report. This task adds no combined score or scheduler.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| I01-01 | P/B | Run all three agents for one company: each has its own run ID, status, evidence, and score; one failure does not replace another agent's successful result. |
| I01-02 | P/B | Run agents for two companies concurrently: no result, chunk, article, chart, or polling response appears under the wrong company. |
| I01-03 | P/B | Restart API and analysis worker during work: completed history remains; eligible interrupted work is recovered once and cannot be overwritten by an expired owner. |
| I01-04 | P/B | Run document ingestion while analysis executes: ingestion continues on its worker; analysis does not claim or mutate ingestion jobs. |
| I01-05 | B | Reload, switch companies/tabs, and rerun an agent: history survives; active polling resumes; previous successful result remains available. |
| I01-06 | P/B | Edit a company after completion, then remove an original document: historical company/evidence snapshots remain readable and unavailable original links are labeled. |
| I01-07 | U/P/B | Execute all new automated tests, existing backend tests, and frontend build: no unexplained regressions or skips in required configured suites. |
| I01-08 | L | Run one complete real-provider workflow per agent, including a real chart-image request: record data dates, scores, citations, timing, and provider/model versions; all track quality gates hold. |
| I01-09 | B | Inspect desktop, mobile, 200% zoom, keyboard-only navigation, and error recovery across all three result views: content remains usable and follows `design.md`. |

**Done when:** all automated cases pass, live gates are recorded as passed, startup/configuration instructions work from a clean checkout, and remaining non-blocking limitations are explicitly documented.
