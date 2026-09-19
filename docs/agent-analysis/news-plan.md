# News agent implementation plan

Progress: [task status tracker](status.md#news-agent). **Entry prerequisite: common/C10 is complete.** Reuse common configuration, Azure models, ticker context, execution limits, evidence ledger, persistence, scoring utilities, and UI shell.

Read [task execution and validation rules](README.md) and [the master plan](../../plan.md). This track retrieves company news through Tavily, analyzes distinct events, and scores their implications over **2–8 weeks**. It does not download financial reports, compute technical indicators, or crawl arbitrary sites.

## Deliverables and fixed decisions

- Implement under `backend/app/analysis/news/`, separating Tavily access, article normalization, event grouping, scoring, and agent orchestration.
- Search the preceding 30 days relative to frozen UTC assessment time. Events first published within the latest seven days get recency weight 2; older eligible events get 1.
- Limits: six searches, one extraction batch of at most ten discovered URLs, at most 30 retained distinct articles, and 30,000 evidence tokens across the run. All common time/model/retry limits also apply.
- Sentiment direction: 0 is very adverse, 5 neutral/mixed, 10 very favorable. Confidence is evidence quality, not sentiment.
- Score one distinct event once regardless of article volume. Store publication/retrieval timestamps and original/canonical URLs, and preserve conflicting evidence.

## N01 — Tavily configuration and bounded provider adapter

**Status:** [See tracker](status.md#news-agent). **Depends on:** common/C10.

**Implementation**

- Add compatible `tavily-python` and a narrow injected provider interface. Obtain its key lazily using common `TAVILY_API_KEY_SECRET` and the existing Key Vault secret provider.
- Expose search and extraction operations with explicit timeouts, common retry policy, provider response normalization, and safe error translation.
- Configure news-topic searches with explicit date bounds when supported by the selected SDK; always post-filter dates in N02 because provider filtering is not sufficient evidence of recency.
- Disable provider-generated answer text as a source of truth. Retain attributable article content/excerpts and URL metadata, not an uncited synthesized provider answer.
- Extract only URLs returned by this run's searches. Limit the one extraction batch to ten URLs; disallow arbitrary model-supplied addresses and local/private-network URLs.
- Persist request metadata and retrieval timestamps without API keys or raw exception payloads.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N01-01 | U | Instantiate other agents with missing Tavily setting: no secret lookup; news request yields clear configuration failure. |
| N01-02 | U | Inject secret/client stubs: key obtained lazily, cached by resource pattern, absent from logs/result/API snapshots. |
| N01-03 | U | Search captures topic/date/window/limit parameters: scoped news request and no dependency on provider-generated answer text. |
| N01-04 | U | 429/timeout/5xx versus auth/quota configuration failure: bounded transient retries only, with safe typed errors. |
| N01-05 | U | Extraction asks for a discovered public URL, an undiscovered URL, localhost/private IP, or eleven URLs: only valid discovered public targets within cap are accepted. |
| N01-06 | U | Empty search, malformed response, and one failed URL in extraction batch: empty evidence differs from provider failure; per-URL failure preserves other usable evidence. |

**Done when:** Tavily can be called safely and predictably through run-scoped tools without becoming a dependency of unrelated agents.

## N02 — Article identity, date filtering, and evidence storage

**Status:** [See tracker](status.md#news-agent). **Depends on:** N01.

**Implementation**

- Normalize title, publisher/domain, original URL, canonical URL, publication timestamp/precision, retrieval timestamp, content/excerpt, content hash, and evidence ID.
- Canonicalize URLs by removing fragments and known tracking parameters while preserving content-identifying query parameters. Do not change paths or collapse distinct articles solely because they share a domain.
- Determine company relevance using its name, canonical ticker/base symbol, and corroborating business context from title/content. A substring match or ambiguous abbreviation alone is insufficient; record match evidence and rejected/uncertain candidates.
- Keep dated articles in `[as_of - 30 days, as_of]`. Exclude future/old dates from scoring. Retain undated/invalid-date items only as labeled background, never as numerical evidence.
- For date-only publications, compare UTC calendar dates and record date precision instead of inventing a time. Timestamped publications use their supplied timezone and normalize to UTC; timezone-free date-time values are background-only unless the provider explicitly establishes their timezone. Disclose the date-only convention.
- Persist bounded supporting excerpts under the shared evidence budget. Retain all material conflicting snippets needed to explain an event; truncation flags reduce coverage/confidence instead of implying comprehensive coverage.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N02-01 | U | Article clearly names the company/ticker, a foreign namesake, a sector-only article, and an ambiguous abbreviation: only supported company-specific matches qualify. |
| N02-02 | U | Publications exactly at 30-day start, exactly at assessment time, one instant outside each bound: only inclusive-window dates qualify. |
| N02-03 | U | IST/UTC timestamp variants, date-only values, missing/invalid dates, and future dates: stable classification with precision retained; no invented timestamp. |
| N02-04 | U | URLs differ by tracking fragment versus meaningful article query ID: tracking duplicates canonicalize; distinct content IDs stay distinct. |
| N02-05 | U/P | Save/read article evidence: title, URL, publisher, publication/retrieval times, excerpt, match evidence, and hash survive. |
| N02-06 | U | Oversized or markup-laden content: capped evidence tokens, explicit truncation, and safe text; script/instruction text cannot change tool scope. |

**Done when:** retained evidence has defensible company identity, dates, and provenance; recent-search results cannot be scored merely because Tavily returned them.

## N03 — Duplicate articles and distinct event grouping

**Status:** [See tracker](status.md#news-agent). **Depends on:** N02.

**Implementation**

- Deduplicate exact canonical URLs/content hashes, then group syndicated/near-duplicate reporting into events using company, event type, event date, named counterparties, and material facts. Model-assisted grouping must cite articles and pass membership validation.
- An event stores a stable run-local ID, short description, type, dated source IDs, earliest credible publication of that same development, and source disagreements.
- Keep follow-up developments separate only when they contain a material new fact, such as a later regulatory decision or revised earnings figure. Mere reposting or commentary is not a new event.
- Corrections to an event amend its factual interpretation and preserve contradictory evidence; they do not count twice. Reposting does not refresh an old event into the seven-day recency window.
- Cap retained distinct articles at 30 using latest publication first with stable URL tie-breaking after exact deduplication; keep exclusion counts/limitations. The model must not claim the search captured all market news.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N03-01 | U | One announcement appears at five syndicated URLs: one event with multiple supporting source IDs, no fivefold scoring weight. |
| N03-02 | U | Two announcements from the same publisher/company on the same date but different counterparties/material facts: remain separate events. |
| N03-03 | U | Ten-day-old event reposted yesterday: event recency remains older weight 1 unless the newer article documents a material new development. |
| N03-04 | U | Original claim followed by a correction/denial: one event preserves disagreement/correction and does not count original and correction as independent sentiment votes. |
| N03-05 | U | Material follow-up regulatory decision after an earlier investigation: separate dated developments with explicit relationship, not accidental merging. |
| N03-06 | U | More than 30 unique articles and shuffled input order: deterministic retention, no duplicate IDs, truncation disclosed. |
| N03-07 | U | Grouping output refers to unknown article IDs, another company, or assigns the same article to conflicting duplicate events: validator rejects invalid membership. |

**Done when:** repeated media coverage does not inflate sentiment and material developments remain distinguishable.

## N04 — Agentic news research and event assessments

**Status:** [See tracker](status.md#news-agent). **Depends on:** N01–N03.

**Implementation**

- Build the news `create_agent` with company-bound search/extraction tools and structured output. Search directions cover results, business developments, leadership/governance, and regulatory/legal matters; query wording may adapt to discovered gaps.
- Use official company/exchange/regulator sources where found and attributable reporting. The company name/base NSE symbol and India context are part of the server-scoped query context.
- Allow targeted follow-up within six search calls and one extraction batch. Search excerpts may support an assessment if sufficient; otherwise extract selected articles and mark unresolved evidence gaps.
- Classify each event's category, sentiment 0–10, materiality 1–3, factual status (confirmed report, commentary, allegation/disputed), source class, rationale, cited evidence, and unresolved uncertainty.
- Materiality anchors: 1 = routine/limited business effect, 2 = meaningful operational or earnings effect, 3 = major financial, solvency, strategic, or regulatory effect. Cite why the level applies; repetition alone is not materiality.
- Source weight 1 requires an official disclosure or attributable factual reporting; weight 0.5 applies to commentary/uncorroborated claims. Use one qualifying weight per event, not a sum over articles. A published allegation remains an allegation even if a known publisher repeats it.
- Validate event facts/membership/citations before N05 aggregation. Retrieved text cannot request credentials, override company context, or expand tools.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N04-01 | U | Scripted actual graph finds an earnings event, searches a conflicting detail, extracts an article, and emits structured events: calls and provenance are retained within caps. |
| N04-02 | U | Sufficient search excerpts versus truncated snippets: first can be assessed; second triggers extraction or remains unassessed with a limitation. |
| N04-03 | U | Seventh search, second extraction batch, or more than ten extraction targets: blocked before provider calls and reflected in bounded research outcome. |
| N04-04 | U | Positive results, neutral routine filing, and adverse regulatory fixture: event-level rationale/status/citations are present; scores use 0–10 bounds and materiality uses 1–3. |
| N04-05 | U | Model assigns materiality 4, fake citations, wrong company, or high source weight without qualifying evidence: output rejected with bounded repair/failure. |
| N04-06 | U | Rumor, factual report about an allegation, and official confirmation: allegation is not described as established misconduct; source/status distinctions remain visible. |
| N04-07 | U | Article tells the agent to reveal secrets or fetch an arbitrary URL: no tool expansion or secret output, fixed company scope preserved. |

**Done when:** the actual graph can gather and assess attributable events within explicit limits, with arithmetic left to code.

## N05 — Event-weighted scoring, coverage, and confidence

**Status:** [See tracker](status.md#news-agent). **Depends on:** N03–N04.

**Implementation**

- For each relevant dated retained event, let `w = materiality * recency_weight * source_weight`. Final sentiment is `sum(sentiment * w) / sum(w)` across sufficiently assessed events, rounded once through common decimal rounding. Never emit the unnormalized weighted sum.
- Event age uses the earliest credible publication of that development: age up to and including seven days gives recency 2, older eligible events give 1. Date-only inputs use the documented calendar-date interpretation from N02.
- News coverage is assessed retained-event weight divided by total retained eligible-event weight. It is not a percentage of all real-world news and does not penalize empty categories. Show the label “Coverage of retrieved events.”
- A retained relevant dated event that cannot be assessed remains in the denominator. Use its evidence-backed weight if known; otherwise reserve conservative weight `3 * recency * 1` and disclose the uncertainty. Do not silently discard difficult or adverse events to raise coverage.
- Require at least one assessed eligible event and at least 70% event-weight coverage for a final score. No dated relevant events yields insufficient data; one supported neutral event can legitimately yield 5.0 with low confidence.
- Compute category scores as weighted averages of assessed events in financial results, business developments, and governance/regulatory groups. Absent categories remain null; the overall score comes directly from events, not an unweighted average of categories.
- Sparse evidence (one event), unresolved material disagreement, uncertain dates, or search truncation lowers confidence. High confidence requires at least three distinct assessed events, 100% retained-event coverage, independently attributable sources, and no unresolved material contradictions; this describes this retrieved evidence, not an exhaustive market view.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N05-01 | U | Event A score8/materiality3/recent2/source1 and B score2/materiality1/older1/source0.5: weighted average `(48+1)/6.5` rounds to 7.5, never 49. |
| N05-02 | U | Same event gains ten duplicate articles: event weight/final score unchanged; source class changes only with new qualifying corroboration. |
| N05-03 | U | Exactly seven days old versus seven days plus one instant, and equivalent date-only cases: defined recency boundary is applied consistently. |
| N05-04 | U | No relevant dated events, only undated background, one neutral event, and all negative events: null/null/5.0/adverse score, respectively. |
| N05-05 | U | Assessed weight is exactly 70%, below 70%, or zero; one unassessed event lacks materiality: proper eligibility, conservative denominator, no division by zero. |
| N05-06 | U | All events fall in business developments: overall score remains valid, other category scores null, coverage reflects events rather than absent categories. |
| N05-07 | U | Category populations/weights differ sharply: final equals direct event-weighted result, not the average of category averages. |
| N05-08 | U | One event, three corroborated events, or unresolved conflicting reports: confidence low/high only when criteria hold; numerical score is not repurposed as confidence. |
| N05-09 | U | Events are shuffled, scores at 0/10 boundaries, or one is NaN: stable bounded average for valid inputs; invalid numeric event rejected. |

**Done when:** final/category scores can be independently reproduced, duplicate publicity cannot inflate them, and missing evidence is distinguishable from neutrality.

## N06 — News result and event evidence view

**Status:** [See tracker](status.md#news-agent). **Depends on:** N04–N05; common UI available.

**Implementation**

- Register the completed adapter and publish research/normalization/event-assessment/scoring stages through the common runtime.
- Add a result renderer with final sentiment, 30-day search window, 2–8 week outlook, confidence, retrieved-event coverage, category breakdowns, and dated event list.
- Each event shows sentiment, materiality, factual status, rationale, publisher/date/source links, and saved supporting excerpt. Show multiple articles under one event without implying multiple votes.
- Distinguish no recent news, undated background, provider failure, sparse coverage, and conflicting reports. External links use safe HTTP(S) URLs and safe new-tab behavior.
- Reuse common history/polling; render provider content as safe text and retain snapshots when external links disappear.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N06-01 | B | Complete mixed-news fixture: final/category scores and dated distinct events agree with the stored result. |
| N06-02 | B | Syndicated articles and disputed allegation: one event with several sources, visible disputed/attributed status, no asserted unproven fact. |
| N06-03 | B | No news, one neutral event, undated-only background, and provider failure: distinct states; neutral 5 appears only for supported neutral evidence. |
| N06-04 | B | Unsafe link/markup fixture and unavailable external article: no executable content, safe links only, saved excerpt remains readable. |
| N06-05 | B | Switch company/history during delayed results; use keyboard/mobile/200% zoom: correct run persists and event/source controls remain accessible. |

**Done when:** the user can trace sentiment to distinct dated events and distinguish evidence limitations from sentiment direction.

## N07 — News acceptance suite and handoff

**Status:** [See tracker](status.md#news-agent). **Depends on:** N01–N06.

**Implementation**

- Maintain reviewed synthetic article/event fixtures for favorable/adverse/mixed news, neutrality, no news, namesakes, syndication, conflicting reports, undated sources, and temporal boundaries.
- Test API → worker → Tavily fixture → actual graph with fake model → event normalization/scoring → persisted result/UI. Stub the external network, not the domain deduplication/scoring pipeline.
- Run the shared three-run Azure evaluation standard on fixed favorable/adverse/mixed evidence sets. Add a live Tavily+Azure workflow for an approved Indian company, recording the actual news window and URLs.
- Document configuration/secret-name setup, search caps, missing-publication behavior, provider errors, and scoring formula. Record coverage, versions, live observations, and implementation commit.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| N07-01 | P/A | End-to-end fixtures produce the expected event groups, source references, coverage, and independently calculated sentiment. |
| N07-02 | U/P | Add duplicate syndicated stories, wrong-company hits, future/old articles, or undated sources: final score changes only for new eligible material evidence. |
| N07-03 | P/B | Rerun/recover and later lose an external URL: frozen assessment window remains stable, source snapshots/history remain reviewable. |
| N07-04 | U/P/B | All Nxx tests, common/provider regressions, frontend build, and coverage checks pass with recorded results. |
| N07-05 | L | Live Tavily search/extraction: scoped company/date results are attributable; undated/unmatched content is filtered; key/exception secrets never enter evidence/logs. |
| N07-06 | L | Three fixed-evidence evaluations per representative scenario: material facts are supported, rumors remain attributed, duplicates do not amplify score; score ranges and contradictions reviewed. |
| N07-07 | L/B | Approved company runs from UI through Tavily and Azure: final saved score recalculates from events and source/date explanations survive refresh. |

**Done when:** automated and live gates pass and news analysis runs independently of the fundamental/technical tracks.
