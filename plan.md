# Three independent company-analysis agents

Detailed implementation and validation tasks are in the [task pack](docs/agent-analysis/README.md):

- [Common foundation — C01–C10](docs/agent-analysis/common-plan.md)
- [Fundamental agent — F01–F07](docs/agent-analysis/fundamental-plan.md)
- [Technical agent — T01–T07](docs/agent-analysis/technical-plan.md)
- [News agent — N01–N07](docs/agent-analysis/news-plan.md)

Complete the common foundation first. Each agent track then assumes those shared interfaces and services are available. The task pack also includes cross-agent acceptance task I01. Current task statuses, validation notes, and completion counts are maintained in the [task status tracker](docs/agent-analysis/status.md).

## 1. Outcome and architecture

Build three independently runnable agents using **`from langchain.agents import create_agent`**, followed by an Agentic Analysis UI for selecting a company, running each agent, and reviewing saved results.

| Agent | Evidence | Assessment |
|---|---|---|
| Fundamental | Latest completed annual report in the existing vector database | Financial health, interpreted for the company’s sector |
| Technical | Yahoo Finance daily prices and a generated chart | Technical outlook over 2–8 weeks |
| News | Recent company news retrieved through Tavily | News sentiment and implications over 2–8 weeks |

Each agent returns parameter scores and its own final score out of 10. A combined score across all three agents is outside this version.

**Reuse the existing application:** FastAPI, SQLAlchemy/PostgreSQL, pgvector hybrid retrieval, Azure resource clients, document storage conventions, and React design baseline. Introduce a separate durable analysis worker so analysis does not block API requests or document ingestion.

### Shared contracts

- Agent interface: `run(context) -> AgentResult`. Context contains the selected company, run ID, immutable run-start timestamp, model configuration, and execution limits.
- Result includes agent type, company/ticker snapshot, assessment date, evidence dates, summary, parameter scores, final score, confidence, coverage, strengths, risks, limitations, and source references.
- Each parameter includes its name, weight, nullable score, explanation, and evidence references.
- Persist model/deployment, prompt version, scoring version, tool activity, token usage where available, and timing.
- Persist evidence excerpts and input snapshots so historical results remain understandable after source documents change or disappear.
- Use Pydantic schemas with `create_agent(..., response_format=ToolStrategy(...))`; consume the validated `structured_response`.
- Bind company identity and permitted documents server-side. The model cannot change company scope through tool arguments.

### Scoring convention

- **0–2:** very weak/adverse; **3–4:** weak/adverse; **5:** mixed or neutral; **6–7:** favorable; **8–10:** strongly favorable.
- Higher always means healthier or more favorable.
- The model assigns evidence-supported parameter scores; application code calculates the weighted final score, rounded to one decimal.
- Missing evidence produces an unscored parameter, never an invented neutral score.
- For fundamental and technical results, calculate a final score only when supported parameters cover at least 70% of the configured weight and the agent’s required evidence is present. Normalize the weighted sum by the supported weight. Otherwise return `insufficient_data`.
- News uses a normalized event-weighted average and requires at least 70% coverage of retained eligible-event weight; absent news categories are not missing parameters. This coverage does not measure all real-world news.
- Confidence and evidence coverage remain separate from the score.

## 2. Agent specifications

### Fundamental agent

**Evidence selection and retrieval**

1. Resolve the company and select its latest non-deleted, completed annual report with compatible embeddings.
2. Report the selected fiscal year explicitly. Flag newer reports still ingesting or failed; never present an older report as current-year evidence.
3. If no usable report exists, return `insufficient_data` with an upload or ingestion recovery action.
4. Reuse existing semantic-plus-keyword retrieval through a service extracted from the document-search endpoint. Preserve the existing endpoint’s behavior.
5. Expose bounded tools for searching the selected report and reading nearby chunks or pages from that report.
6. Search the financial statements, notes, audit opinion, management discussion, risks, and related-party disclosures. Follow up on missing evidence and contradictory findings.
7. Use comparative figures contained in the selected report; do not retrieve earlier reports in this version.

**Parameters**

| Parameter | Weight | Operating-company interpretation |
|---|---:|---|
| Growth and business resilience | 15% | Revenue/earnings movement, concentration, durability |
| Profitability and efficiency | 20% | Margins, returns, operating efficiency |
| Balance-sheet strength | 20% | Debt, solvency, interest coverage |
| Cash generation and liquidity | 20% | Operating cash flow, earnings conversion, liquidity |
| Governance and reporting quality | 15% | Audit findings, related parties, contingencies |
| Outlook and business risks | 10% | Management outlook, commitments, material risks |

Keep these six dimensions across sectors, with sector-specific evidence:

- **Banks:** NIM, ROA/ROE, GNPA/NNPA, provisions, capital adequacy, deposits, and liquidity.
- **NBFCs:** spreads, asset quality, capital adequacy, funding concentration, and asset–liability maturity.
- **Insurers:** premium growth, underwriting performance, claims, solvency, reserves, and investment exposure; distinguish life and general insurers.
- Infer the profile from cited report content. If classification is ambiguous, abstain from a final score rather than applying unsuitable ratios.

**Evidence quality**

- Prefer consolidated statements when available; label standalone-only analysis.
- Preserve fiscal period, currency, units, and accounting basis for every extracted financial metric.
- Calculate derived ratios in code from cited inputs. Do not let the model invent missing numbers or mix consolidated and standalone values.
- Profitability and balance-sheet evidence are required for a final score.
- Cite report, fiscal year, chunk ID, and page for material findings.
- Describe financial health as of the report period. Valuation and price targets are outside this agent’s scope.
- Allow up to 12 retrieval/read calls, with bounded evidence context and a five-minute run deadline.

### Technical agent

**Market data**

- Use `yfinance` behind an application-owned Yahoo Finance adapter.
- Normalize bare NSE symbols to uppercase `.NS`, for example `reliance` → `RELIANCE.NS`.
- Reject explicitly different exchanges and non-equity symbol formats instead of appending `.NS` blindly.
- Fetch one year of daily OHLCV data with adjustment behavior explicitly configured. Use consistently adjusted OHLC for indicators and candles, and label this in the chart.
- Preserve the fetched dataset and adjustment metadata.
- Interpret trading dates in `Asia/Kolkata`; exclude the current session until 16:00 IST.
- Sort and deduplicate rows, validate OHLC relationships, and do not fill missing trading sessions.
- Require at least 60 valid completed sessions. Flag prices older than seven calendar days.

**Indicators and chart**

Calculate in code:

- **MACD:** EMA(12) − EMA(26), signal EMA(9), and histogram.
- **RSI:** 14-period Wilder smoothing, with defined initialization and zero-gain/loss handling.

Generate one PNG with four aligned panels:

1. Candlesticks.
2. Volume.
3. MACD, signal, and histogram.
4. RSI with 30/70 reference lines.

Display the latest 126 sessions, or all available sessions when fewer exist. Compute indicators on the full fetched history before trimming the display.

Use Matplotlib/mplfinance with a headless backend. Store the chart under the run’s artifact directory.

**Multimodal assessment**

- Build the chart before invoking the technical agent.
- Send the actual image content to a vision-capable Azure deployment, together with precise latest indicator values and data dates.
- Expose a bounded tool for inspecting the saved numerical series.
- Score price structure/trend **30%**, MACD momentum **25%**, RSI condition **25%**, and volume confirmation **20%**.
- Explain agreement or disagreement between signals; do not automatically treat overbought as bearish or oversold as bullish.
- Require successful image delivery and valid MACD/RSI data for a final score. A failed vision call must not silently become a text-only result.

### News agent

**Retrieval**

- Wrap `tavily-python` in company-scoped LangChain tools.
- Resolve the Tavily key through the existing Key Vault secret-provider pattern. Configure the secret name without storing the key in source or browser code.
- Search the preceding **30 days**, emphasizing developments from the latest seven days.
- Use company name, NSE symbol, and India context across results, business developments, management, regulatory, and legal queries.
- Allow up to six searches and one extraction batch for at most ten selected URLs; retain at most 30 distinct articles.
- Extract content through Tavily where search excerpts are insufficient. Do not implement an unrestricted website crawler.

**Evidence processing**

- Store title, URL, publisher, publication timestamp, retrieval timestamp, and supporting excerpt.
- Filter wrong-company matches and articles outside the window.
- Exclude undated articles from numerical scoring, while allowing clearly labeled background context.
- Deduplicate syndicated stories and group reports describing the same event.
- Preserve conflicting reports and distinguish confirmed announcements, commentary, and allegations.

**Scoring**

- Give each distinct event a sentiment score from 0–10, a materiality level of 1–3, and a cited explanation.
- Weight events from the latest seven days twice as heavily as older events.
- Use source weights of 1 for official disclosures or attributable reporting, and 0.5 for attributed commentary or uncorroborated claims.
- Calculate the final score in code as `sum(sentiment * event_weight) / sum(event_weight)` over assessed events, where `event_weight = materiality * recency * source_weight`. Multiple articles about one event do not multiply its influence. Coverage compares assessed event weight with total retained eligible-event weight, as detailed in news/N05.
- Show category breakdowns for financial results, business developments, and governance/regulatory events where evidence exists.
- No relevant dated news means `insufficient_data`, not 5/10. Sparse or disputed evidence lowers confidence.

## 3. Session-sized implementation tasks

The table below records the original coarse milestones. The [detailed task pack](docs/agent-analysis/README.md) expands them into 32 tasks grouped into common, fundamental, technical, news, and integration plans. Each task section defines prerequisites, deliverables, explicit test scenarios and expected results, and a completion gate; the index provides the milestone mapping and session handoff template.

| Task | Dependencies | Deliverable and acceptance |
|---|---|---|
| **S01 — Contracts and task pack** | None | Create the implementation task documents, shared Pydantic result/context schemas, scoring conventions, and representative fixtures for all three agents. Validate score bounds, missing evidence, coverage, and weighted aggregation. |
| **S02 — LangChain and model integration** | S01 | Add compatible LangChain and Azure integration dependencies; extend the resource layer with model factories and per-agent deployment overrides, defaulting to Terra. Verify tool calling, structured output, and image input. Current `openai<2` conflicts with the current LangChain OpenAI dependency, so update and lock compatible versions and regression-test existing embedding/resource calls. |
| **S03 — NSE company contract** | S01 | Implement shared ticker normalization and update add/edit UI, validation, tests, and `design.md`. Preserve readable legacy records; require correction before analysis when their ticker is incompatible. Do not mass-convert existing ambiguous symbols. Check uniqueness after normalization. |
| **S04 — Durable analysis execution** | S01–S02 | Add versioned migrations, run/result persistence, artifact handling, API routes, and a separate analysis worker. Implement leases, heartbeat, ownership-checked completion, bounded recovery, progress, and sanitized errors. Prove that worker restart does not lose queued jobs or allow an expired worker to overwrite results. |
| **F01 — Fundamental retrieval tools** | S01–S02 | Extract reusable hybrid-search logic without changing the existing search API. Add latest-report selection, company-scoped search/context tools, citations, and an evidence ledger. Verify company isolation, incomplete ingestion, absent reports, and embedding incompatibility. |
| **F02 — Fundamental agent** | F01, S04 | Implement sector profiles, extraction and calculation helpers, bounded iterative research, structured output, and scoring. Test ordinary companies, banks, NBFCs, insurers, missing statements, conflicting units, and unsupported citations. |
| **T01 — Yahoo data adapter** | S01, S03 | Implement daily-history retrieval, normalization, completed-session filtering, data validation, and saved snapshots. Test provider failure, empty data, invalid symbols, splits, duplicates, stale data, and short histories. |
| **T02 — Indicators and chart artifacts** | T01 | Implement MACD/RSI and the four-panel chart. Verify indicator values against independent reference fixtures, edge cases, warm-up handling, and chart readability. |
| **T03 — Multimodal technical agent** | T02, S02, S04 | Connect image input, numerical inspection tools, structured interpretation, and scoring. Verify the model receives the image bytes, cites valid observations, and reports vision failure explicitly. |
| **N01 — Tavily provider and evidence** | S01–S02 | Add lazy secret resolution, bounded search/extraction tools, article normalization, company matching, date filtering, and event deduplication. Test duplicates, namesakes, missing dates, quota failures, and extraction failure. |
| **N02 — News agent** | N01, S04 | Implement targeted follow-up searches, event assessments, deterministic aggregation, category breakdowns, and citations. Verify neutral news differs from absent news and that duplicate coverage cannot inflate scores. |
| **U01 — Agentic Analysis UI** | S01, S03–S04; fixtures available | Replace the planned page with company selection, three agent tabs, individual run actions, progress, saved history, and result views. Include report citations, chart display, source links, parameter scores, confidence, limitations, and recovery states. Integrate each real agent as it becomes available. |
| **V01 — Integrated validation and handoff** | F02, T03, N02, U01 | Run the complete workflow for representative Indian companies, verify worker recovery and historical results, run regression checks, and document configuration/startup/troubleshooting. Record actual outputs and outstanding limitations. |

After the shared contracts and runtime are complete, the fundamental, technical, and news tracks can be implemented in separate sessions without depending on one another.

**Every completed milestone:** run its relevant checks, update its task/handoff record, and commit only its intended changes. Preserve the existing uncommitted README change. Do not build Docker.

## 4. APIs, UI, and operational behavior

### Public API additions

| Endpoint | Behavior |
|---|---|
| `POST /api/companies/{company_id}/analysis-runs` | Accept `{agent_type}` and return a queued run with HTTP 202 |
| `GET /api/companies/{company_id}/analysis-runs` | Return paginated history, optionally filtered by agent |
| `GET /api/analysis-runs/{run_id}` | Return state, progress, terminal result, or safe error |
| `GET /api/analysis-runs/{run_id}/artifacts/{artifact_id}` | Serve registered artifacts such as the technical chart |

- Run states: `queued`, `running`, `completed`, `insufficient_data`, and `failed`.
- Permit one active run per company and agent; repeated submissions return the existing active run.
- Rerunning creates a new historical record.
- Resolve artifact IDs server-side; never accept arbitrary filesystem paths.
- Preserve analysis history and block company deletion while history exists, consistent with the current document-deletion constraint.
- Use PostgreSQL for durable analysis. Keep the existing SQLite company workflow usable and return an explicit unsupported-configuration response for analysis there.

### Worker and UI behavior

- Use a separate `npm run worker:analysis` command and PostgreSQL job leases.
- Apply provider timeouts and at most two transient retries per request, within a five-minute overall run deadline.
- Recover expired jobs with at most three execution attempts. Persist only the current lease owner’s terminal result.
- Treat retrieved documents and web content as evidence, never as instructions.
- The UI polls active runs, stops polling on terminal states, and ignores stale responses after company/run selection changes.
- Show “Upload annual report,” “Correct ticker,” or “Retry” when applicable.
- Keep prior successful results visible while a new run executes.
- Follow the existing tokens, accessible tabs, compact tables, responsive behavior, and concise copy in `design.md`.

## 5. Validation and implementation defaults

**Required checks**

- Existing backend unittest suite and frontend TypeScript/Vite build.
- PostgreSQL integration tests for migrations, retrieval isolation, duplicate submissions, worker leases, and persisted results.
- Deterministic fixtures for financial calculations, indicators, news aggregation, and missing-data behavior.
- Mocked model tests for malformed structured output, invalid citations, tool limits, and prompt injection in evidence.
- Browser checks for company selection, independent agent runs, page refresh, history, citations, chart rendering, errors, keyboard access, and mobile layout.
- Provider smoke tests using configured credentials, including one actual image-input call. Report missing credentials or unsupported vision capability explicitly.

**Defaults**

- Latest completed annual report only; all requested company sectors supported.
- Daily technical data with **MACD and RSI only**.
- Technical/news outlook: **2–8 weeks**.
- News window: **30 days**, emphasizing the latest seven.
- Existing Azure deployments, defaulting to Terra, with explicit per-agent overrides.
- Manual runs only in v1; no scheduling, trading execution, backtesting, or combined recommendation engine.
- Provider capability checks are implementation gates; deployment names alone do not establish vision support.

Implementation references: [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents), [structured output](https://docs.langchain.com/oss/python/langchain/structured-output), and the shared [retrieval and precedence standard](/home/azureuser/projects/knowledgebase/01-Active-Standards/retrieval-and-precedence.md).
