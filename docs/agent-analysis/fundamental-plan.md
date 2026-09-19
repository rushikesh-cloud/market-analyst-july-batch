# Fundamental agent implementation plan

Progress: [task status tracker](status.md#fundamental-agent). **Entry prerequisite: common/C10 is complete.** Use its model factory, contracts, scoring, evidence ledger, worker, API, and UI shell. Do not rebuild common infrastructure.

Read [task execution and validation rules](README.md) and [the master plan](../../plan.md). This track assesses financial health from the **latest eligible annual report only**, including comparative figures printed in that report. It does not fetch market prices, news, valuation multiples, or older reports.

## Deliverables and fixed decisions

- Implement under `backend/app/analysis/fundamental/`, with separate report selection, retrieval, metrics, sector profiles, and agent modules.
- Construct the agent with `langchain.agents.create_agent`; give it company/report-bound search and contextual-read tools, not arbitrary SQL or web access.
- Six dimensions and weights: growth/resilience 15, profitability/efficiency 20, balance-sheet strength 20, cash/liquidity 20, governance/reporting 15, outlook/risks 10.
- A final score requires at least 70% weighted coverage, supported profitability and balance-sheet findings, an evidence-backed sector profile, and valid citations. Missing metrics remain null; a profile may use suitable narrative or disclosed metrics instead of an inappropriate generic ratio.
- Prefer consolidated reporting. State the report period and accounting basis; do not imply financial information is current to the run date.
- Every material financial fact, risk, and score rationale references saved source evidence. Document text is untrusted data, never a source of instructions.

## F01 — Select and freeze the report context

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** common/C10.

**Implementation**

- Select the highest fiscal-year non-deleted, completed report for the selected company that has compatible embedding metadata and existed at the run assessment time.
- Record report ID, fiscal year, source filename, embedding deployment/dimensions, content/chunking version, and reporting dates when disclosed. Persist this selection on the run so recovery uses the same report.
- Flag newer uploaded reports that are incomplete, failed, or incompatible; disclose any use of an older eligible report. If no eligible report exists, return insufficient data with a specific upload/ingestion recovery action.
- Verify the selected report has indexed chunks; an empty index is insufficient data, not an invitation to invent findings or search a different company.
- Detect source deletion/reingestion between selection and retrieval. Stop with a safe source-changed failure rather than mixing chunk versions; completed result snapshots remain available.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F01-01 | P | Company has completed FY2023/FY2024/FY2025 reports: FY2025 alone is selected, regardless of upload order. |
| F01-02 | P | Latest report is queued/failed/incompatible, earlier report is eligible: earlier report selected with an explicit newer-report warning; no cross-report retrieval. |
| F01-03 | P | No reports, all deleted, no compatible embeddings, or selected report has zero indexed chunks: final score null with the matching recovery reason. |
| F01-04 | P | Another company has a newer and more relevant report: it is never selected or returned. |
| F01-05 | P | A report is uploaded after frozen assessment time, or the run is recovered after a new upload: original eligible selection is retained. |
| F01-06 | P | Selected report is deleted/reingested during execution: source-change error; previously saved complete history remains readable. |

**Done when:** selection is reproducible and never silently changes report or company across tool calls/attempts.

## F02 — Reusable hybrid search and bounded evidence tools

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F01.

**Implementation**

- Extract a reusable search service from the current document-search handler. Preserve query embedding selection, reciprocal rank fusion, stable tie-breaking, whole-chunk budgeting, and existing API responses.
- Expose `search_report(query)` and `read_report_context(chunk_id)` tools, bound to the frozen report. Context returns the target and at most its immediate previous/next chunks; the model cannot supply a new document/company ID.
- Search defaults: up to ten chunks and 6,000 tokens per response, at most 30,000 unique evidence tokens across the run. Count headings/overlap conservatively as ingestion/search does; persist budget/truncation flags.
- Limit the combined search/context calls to 12. Deduplicate repeated chunk evidence before adding to the model context and ledger; original ranked hits remain traceable.
- Save chunk ID, page, heading, excerpt/content, fiscal year, source version, and retrieval query. Neighbor chunks must obey the same ownership/version/budget checks.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F02-01 | P/A | Run existing search fixtures before/after extraction: result order, fusion scores, token counts, error semantics, and endpoint response remain equivalent. |
| F02-02 | P | A foreign report's chunk ranks highest globally: neither search nor contextual read returns it. |
| F02-03 | U/P | Request first/last/middle chunk context: only existing immediate neighbors in the same selected report are returned. |
| F02-04 | U/P | Whole chunk exceeds per-call budget or cumulative evidence reaches 30,000 tokens: omit excess content, report truncation, and stay within the cap. |
| F02-05 | U | Repeated queries return the same chunks and a thirteenth call is attempted: evidence is deduplicated and call 13 is blocked before provider/database retrieval. |
| F02-06 | U/P | Stored embedding deployment differs from current default, or embeddings fail dimension/finite-value validation: stored compatible deployment is used; invalid vector fails safely. |
| F02-07 | U | Chunk text says to change company, fetch a URL, or ignore scoring rules: tool scope remains fixed; no new capabilities are exposed. |

**Done when:** existing search behavior is preserved and the agent can obtain sufficient bounded context with verifiable report-local citations.

## F03 — Financial facts, units, and calculation helpers

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F02.

**Implementation**

- Define typed extracted facts with metric key, original label/text, numeric value or null, currency, scale, fiscal period, consolidated/standalone basis, source evidence IDs, and whether reported or derived.
- Preserve original values and normalize compatible INR rupee/lakh/crore scales for calculations. Parse parentheses and explicit negatives; do not treat an em dash or blank as zero.
- Prefer consolidated facts consistently; retain standalone facts separately. Detect conflicting same-period facts and explain unresolved discrepancies rather than averaging them.
- Implement only applicable formulas with cited inputs: revenue growth, net margin, operating-cash/profit conversion, debt/equity, interest coverage, current ratio, free cash flow, ROA, and ROE. Return null with a reason when inputs/basis/periods are incompatible.
- Use `(current - prior) / prior * 100` for growth only with positive prior revenue; average opening/closing assets or equity for derived ROA/ROE; free cash flow is operating cash flow minus positive capex outflow. Preserve directly reported ratios with their source label if derivation inputs are absent.
- Zero/negative denominators do not yield misleading ratios: retain the underlying financial problem and label the derived metric not meaningful. Monetary currency conversion is outside this version.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F03-01 | U | Revenue rises from INR100 crore to INR120 crore: growth 20%; net profit INR12 crore on INR120 crore revenue gives 10% margin. |
| F03-02 | U | Equivalent values in rupees/lakhs/crores: same normalized arithmetic, original display units and citations retained. |
| F03-03 | U | Zero/negative prior revenue, zero interest/equity, negative profit in cash-conversion ratio, or missing average assets: derived ratio null with a precise reason, no infinity or favorable invented score. |
| F03-04 | U | Consolidated revenue and standalone profit, different fiscal periods, or different currencies: calculation refused rather than mixing bases. |
| F03-05 | U | Parenthesized loss, blank cell, dash, percentage, or ambiguous unit: correct negative/percentage handling; missing/ambiguous values remain unknown. |
| F03-06 | U | Operating cash 80, capex outflow 30, debt 200, equity 100: FCF 50 and debt/equity 2; reversing capex sign is not silently accepted. |
| F03-07 | U | Duplicate or conflicting figures for one metric/period: exact duplicates consolidate provenance, conflicts remain visible and cannot silently feed a derived ratio. |
| F03-08 | U | Model supplies a numeric fact without evidence or fabricated source ID: reject it from the metric ledger and final score support. |

**Done when:** every derived number is reproducible from compatible cited inputs and uncertain data cannot masquerade as zero.

## F04 — Sector profiles and scoring rubrics

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F03.

**Implementation**

- Add explicit profiles for operating companies, banks, NBFCs, life insurers, and general insurers. Infer the profile from cited business descriptions/disclosures; ambiguous mixed businesses abstain from a final score.
- Keep the six shared dimensions and weights, but give each profile its own evidence checklist and qualitative anchors for 0–2, 3–4, 5, 6–7, and 8–10.
- Operating companies use margins/returns, leverage/coverage, cash generation, concentration, audit quality, and disclosed outlook. Banks use NIM/returns, GNPA/NNPA/provisions, capital adequacy, funding/deposits, liquidity, and governance.
- NBFCs use spreads, asset quality, capital, funding concentration, and maturity mismatch. Life insurers use premium growth, persistency, disclosed value-of-new-business measures, solvency and reserves; general insurers use underwriting/combined ratios, claims, reserves, and solvency.
- Do not apply industrial debt/equity or operating-cash conversion thresholds to banks/insurers. Use regulatory minima only if actually evidenced with jurisdiction/date; avoid invented universal numeric cutoffs.
- Score documented adverse findings as low scores, not missing evidence. An unqualified audit alone does not prove excellent governance; absence of disclosed trouble is not proof of strong controls.
- Required profitability and balance-sheet evidence must be appropriate to the selected profile. Version prompts/rubrics and use common/C02 arithmetic and confidence rules.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F04-01 | U | Labeled fixtures for operating company, bank, NBFC, life insurer, and general insurer: correct evidence-backed profile/checklist and all six stable dimensions. |
| F04-02 | U | Bank has high debt/equity typical of its business: generic industrial leverage penalty is not applied; asset quality/capital evidence drives solvency. |
| F04-03 | U | Insurer has underwriting losses or weak solvency: appropriate insurance findings support adverse scores; industrial cash-conversion checks do not determine the score. |
| F04-04 | U | Unsupported or ambiguous profile: final score null and explicit classification limitation, even if generic coverage appears high. |
| F04-05 | U | Missing governance/outlook versus a documented audit qualification: missing stays unscored; qualification produces a cited adverse assessment. |
| F04-06 | U | Covered weight is 70/100 but profitability or balance-sheet support is absent: insufficient data; both gates present at 70% produces the normalized score. |
| F04-07 | U | Fully cited dimension scores change order or model supplies a different weight: server rubric weights prevail and final arithmetic remains stable. |

**Done when:** each supported sector has a reviewable versioned rubric and profile-specific mandatory evidence tests.

## F05 — Iterative fundamental research agent

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F01–F04.

**Implementation**

- Build `create_agent` with a financial-analysis expert prompt, typed tools, and structured output. Initial instructions cover the six dimensions and sector identification; subsequent queries target gaps or contradictions.
- Allow the model to choose query wording and follow-ups within the 12-call/evidence/time/model budgets. Stop early when sufficient evidence exists; do not require a fixed number of iterations.
- Require only retrieved evidence for findings and calculations. Validate returned facts/citations, apply profile gates, calculate final score in code, and persist concise findings rather than hidden chain-of-thought.
- Register the adapter with shared execution. Publish progress such as selecting report, gathering evidence, assessing health, and validating result.
- If evidence remains thin after bounded research, return an explicit insufficient-data or eligible partial-coverage result. Provider/system failure remains failed. Include report period, basis, profile, key metrics, strengths, risks, and limitations.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F05-01 | U | Scripted model first finds profit but misses debt, then searches liabilities: actual graph performs the follow-up and produces a citation-backed complete result. |
| F05-02 | U | First searches provide all required evidence: agent stops without consuming all 12 tool calls. |
| F05-03 | U | Searches never find profitability/balance-sheet evidence: bounded termination, insufficient data, null final score, and missing-evidence explanation. |
| F05-04 | U | Model cites a foreign/unretrieved chunk or invents a metric: finalizer rejects it and bounded repair can correct it; persistent invalidity fails without publication. |
| F05-05 | U | Source instructions request web access or secrets: no such tools execute and the company/report scope stays unchanged. |
| F05-06 | U/P | Embedding outage, model timeout, and empty but successful retrieval: first two are safe failures; genuinely missing evidence is insufficient data. |
| F05-07 | U/P | Recover a run after partial retrieval: selected report and assessment time remain stable, budgets are not silently reset, completed result is written only by the lease owner. |

**Done when:** the actual LangChain graph can research iteratively, abstain appropriately, and produce a validated independent fundamental result through the common runtime.

## F06 — Fundamental result view

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F05; common UI available.

**Implementation**

- Add a dedicated renderer to the shared analysis page: report fiscal year, reporting basis, sector profile, final/dimension scores, metric table with units/periods, confidence/coverage, strengths, risks, and limitations.
- Link citations to the existing document view/page where available; also show the saved excerpt so history remains usable after source deletion.
- Show a clear upload/ingestion action for missing reports and a warning when an older completed report was used. No current-price or buy/sell widget.
- Keep all data server-backed and reuse shared loading/history/polling behavior and design tokens.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F06-01 | B | Complete operating-company/bank fixtures: correct sector labels, report period, scores, metric units, and coverage are visible. |
| F06-02 | B | Open a citation: correct document/page is identified and saved excerpt is accessible; deleted source still displays the snapshot. |
| F06-03 | B | Missing report, newer report ingesting, and partial metric coverage: appropriate recovery/warning, no misleading neutral scores or current-year claim. |
| F06-04 | B | Select old result while a rerun is active: correct report/result stays selected and no stale response changes its company. |
| F06-05 | B | Long headings, negative numbers, source markup, mobile width, and keyboard navigation: readable tables, safe text, accessible citation controls. |

**Done when:** a user can inspect why the score was assigned and which report/figures support it.

## F07 — Fundamental acceptance suite and handoff

**Status:** [See tracker](status.md#fundamental-agent). **Depends on:** F01–F06.

**Implementation**

- Build synthetic annual-report fixtures with reviewed financial values and citations for all five sector profiles, plus a weak/missing-data report and a malicious-content report.
- Add API → worker → actual graph with fake model → saved result integration tests. Reuse real PostgreSQL retrieval with stubbed embeddings; do not replace SQL with a list mock in retrieval acceptance.
- Run the shared live evaluation standard on a representative operating-company and financial-company evidence fixture using Azure; add one approved end-to-end ingested-report smoke check.
- Record coverage, citation review, live observations, prompt/rubric versions, and an implementation commit. Update operating instructions for missing/incompatible reports.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| F07-01 | P/A | For each sector fixture, submit and execute the run: correct selected report/profile, valid citations, and independently recalculated final score. |
| F07-02 | P/A | Missing financial statements, no completed report, or incompatible embeddings: no final number and a precise recoverable outcome. |
| F07-03 | P | Add tempting evidence under another company/year: zero leakage and no cross-year mixing. |
| F07-04 | U/P/B | Execute all Fxx cases plus affected common/search/document regressions and frontend build: all required checks pass with recorded coverage. |
| F07-05 | L | Three repeated representative evidence evaluations: all numerical facts/citations are supported, no generic industrial rubric applied to financial companies, score range reviewed. |
| F07-06 | L/B | Select an approved company with an ingested report and run from UI: live retrieval/model result is saved, citations inspectable, report date/basis clear. |

**Done when:** automated and live acceptance gates pass and the committed track can run without technical or news implementations.
