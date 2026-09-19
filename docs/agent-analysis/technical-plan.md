# Technical agent implementation plan

Progress: [task status tracker](status.md#technical-agent). **Entry prerequisite: common/C10 is complete.** Reuse common ticker validation, Azure vision configuration, execution, scoring, persistence, artifacts, and UI shell.

Read [task execution and validation rules](README.md) and [the master plan](../../plan.md). This track uses Yahoo Finance daily OHLCV, computes **MACD and RSI only**, creates a candlestick/volume/indicator image, and asks a multimodal agent to assess a **2–8 week** outlook. No intraday trading or additional indicators are included.

## Deliverables and fixed decisions

- Implement under `backend/app/analysis/technical/`, separating Yahoo access, dataset validation, indicators, chart generation, and multimodal assessment.
- Use `yfinance` for one year of `interval='1d'` history, with `auto_adjust=True` explicitly set and adjustment metadata recorded. Do not multiply or divide vendor volume to simulate price adjustment.
- Use completed daily sessions, with same-day bars eligible only at/after 16:00 Asia/Kolkata. Do not invent bars for weekends, holidays, or missing sessions.
- Require at least 60 valid completed rows. Chart the most recent 126 rows, or all when fewer, after calculating indicators on full history.
- Fixed scoring weights: price structure/trend 30%, MACD 25%, RSI 25%, volume confirmation 20%. Mandatory gates: usable price data, readable image delivered to the model, valid latest MACD and RSI, and at least 70% supported weight.
- The image is a required model input. Numerical values help validate interpretation; they do not replace vision.

## T01 — Yahoo Finance adapter and daily data snapshot

**Status:** [See tracker](status.md#technical-agent). **Depends on:** common/C10.

**Implementation**

- Add compatible `yfinance`/pandas dependencies and a narrow injected adapter returning typed daily bars plus ticker, request window, fetch timestamp, adjustment settings, and provider/library version.
- Accept only the common context's validated `.NS` ticker. Request one year relative to frozen assessment time; enforce an upper bound on returned dates even if Yahoo returns extra rows.
- Configure request timeout, retry ownership, and adjusted OHLC explicitly. Distinguish successful empty history from transport/auth/rate-limit errors; never silently fall back to another ticker/provider.
- Normalize provider response shapes to one ticker's columns, preserve timestamps, and save the raw normalized snapshot as a registered data artifact for later validation.
- Do not reuse current-time data across a recovered historical run. Once a valid snapshot is stored, subsequent stages/recovery use that same input hash.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T01-01 | U | Invoke adapter for `RELIANCE.NS`: stub captures exact ticker, daily interval, one-year window, explicit adjustment, and bounded timeout. |
| T01-02 | U | Pass `.BO`, bare legacy symbol, or a different ticker in a model tool call: no Yahoo request; context validation/scope rejects it. |
| T01-03 | U | Single-level/MultiIndex-shaped provider fixtures for one ticker: same canonical columns; unexpected extra ticker is rejected. |
| T01-04 | U | Successful empty result, 429 then success, timeout exhaustion, and invalid-symbol response: correct insufficient-data vs provider-failure classification with bounded calls. |
| T01-05 | U/P | Save/fetch snapshot and recover run after provider data changes: stored hash and input bars remain unchanged. |
| T01-06 | U | Split-adjusted fixture and known volume values: adjusted OHLC is used consistently; vendor volume is preserved and adjustment metadata is explicit. |

**Done when:** one scoped reproducible daily dataset is available without coupling provider response details to the indicator/agent code.

## T02 — Trading dates and data-quality rules

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T01.

**Implementation**

- Convert timestamped bars to Asia/Kolkata trading dates; interpret date-only daily rows as provider session labels without shifting to a different date.
- Exclude future rows and the current trading-date row before 16:00 IST. At/after cutoff include it only if actually supplied and otherwise valid; do not assume it exists.
- Sort ascending, collapse identical duplicate sessions, and reject conflicting duplicate sessions rather than arbitrarily choosing one.
- Require finite positive OHLC with `low <= min(open, close) <= max(open, close) <= high`. Reject a malformed dataset explicitly rather than filling invalid prices and fabricating a trend.
- Permit nonnegative volume including zero; all-missing volume remains unscored. Missing-volume bars render gaps and are not forward-filled. Negative/infinite supplied volume is invalid.
- Require at least 60 valid completed sessions; mark last-bar age greater than seven calendar days as stale, retaining the actual as-of date and lowering confidence. Do not fabricate an exchange calendar.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T02-01 | U | Frozen time at 15:59 and 16:00 IST with a valid same-day bar: excluded before cutoff and included at cutoff. |
| T02-02 | U | UTC timezone-aware timestamps and equivalent session-date fixtures: identical trading dates, including UTC/IST date boundaries. |
| T02-03 | U | Weekend/holiday gaps, a future row, and absent same-day data: no filled sessions; future data removed; latest actual completed date retained. |
| T02-04 | U | Unsorted rows plus identical vs conflicting duplicate dates: stable ordered deduplication or explicit conflicting-data failure. |
| T02-05 | U | NaN/infinite/negative prices or impossible OHLC relationships: no chart/score is produced from invalid data. |
| T02-06 | U | Histories with 59 and 60 completed rows: insufficient data versus eligible dataset; incomplete same-day row cannot push 59 over the threshold. |
| T02-07 | U | Zero/missing/negative volume and seven/eight-day-old last bars: zero preserved, missing marked, negative rejected; only age greater than seven is stale. |

**Done when:** all later calculations consume a validated, timestamp-correct dataset with explicit quality flags.

## T03 — MACD and Wilder RSI calculations

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T02.

**Implementation**

- Compute on adjusted close using full valid history. Keep warm-up values unavailable and finite outputs typed; do not replace missing warm-up values with zero.
- MACD: EMA12 and EMA26 use the first close as seed and recursive alpha `2/(span+1)` (`adjust=False`), masked until their respective span of observations exists. MACD begins at observation 26; EMA9 signal is seeded from the first available MACD and exposed after nine MACD values, at observation 34. Histogram equals MACD minus signal.
- RSI14: seed average gains/losses from the first 14 close-to-close changes (15 closes); update with Wilder `(previous_average * 13 + current) / 14`. Positive gains with zero losses yield 100; zero gains with positive losses yield 0; both zero yield 50.
- Export complete timestamped indicator series and a latest-value summary, preserving null warm-up entries in JSON. Save numerical indicators as an artifact with the input hash and calculation version.
- Use hand-reviewed numeric fixtures or an independent reference implementation as test oracles; never compute expected values by calling the implementation under test.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T03-01 | U | Reviewed mixed-price fixture: full valid MACD/signal/histogram values match independent expected values within 1e-8. |
| T03-02 | U | Reviewed Wilder RSI fixture: seed and recursive values match reference within 1e-8, exposing the first RSI at the fifteenth close. |
| T03-03 | U | Constant, strictly rising, and strictly falling closes: RSI 50/100/0 after warm-up; constant prices produce zero MACD/histogram. |
| T03-04 | U | 25/26/33/34 observations: precise MACD/signal availability boundaries; no fabricated warm-up zero. |
| T03-05 | U | MACD values at every valid point: histogram equals line minus signal; RSI stays within 0–100 and all available values are finite. |
| T03-06 | U | Compute full history then select last 126 rows: matches the same tail from the full calculation and does not restart EMA/RSI at display boundary. |
| T03-07 | U | Serialize all outputs: missing values become JSON null, not NaN; timestamps/latest summary align with the final completed bar. |

**Done when:** indicator arithmetic, initialization, boundaries, and serialization are reproducible independent of the model.

## T04 — Four-panel chart image and numerical references

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T03.

**Implementation**

- Add Matplotlib/mplfinance with a headless backend. Render an approximately 1600×1200 PNG with four aligned panels: candlesticks, volume, MACD/signal/histogram, and RSI with 30/70 guides.
- Show ticker, date range, latest completed session, adjusted-price label, price currency when available, and legends. Use readable labels/colors; distinguish lines without relying only on color.
- Display the last 126 sessions or all available sessions, while indicator values remain computed from the full history. Represent missing volume visibly without fabricated bars.
- Publish immutable chart metadata linking PNG, data artifact, indicator artifact, input hash, dates, dimensions, and render version.
- Close figures after rendering. Generate only run-local artifacts and report chart failures before model invocation.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T04-01 | U | Render reviewed 60-row and 252-row fixtures: valid decodable PNG, four panels, correct displayed date range and 60/126 plotted sessions. |
| T04-02 | U | Inspect plotted data/labels through the chart builder: candle/volume/MACD/RSI share dates; RSI guides are 30/70; latest values agree with T03 output. |
| T04-03 | U | Input spans split-adjusted prices and missing volume: no artificial split jump from mixed price bases, and missing volume is not drawn as fabricated data. |
| T04-04 | U/P | Artifact metadata round-trips: image/data/indicator hashes and run IDs agree; another run cannot resolve the image. |
| T04-05 | U | Repeated headless renders and a simulated write failure: figures/resources are released, no partial available chart is registered. |
| T04-06 | B | Review actual PNG at desktop and mobile display sizes: legends, candles, volume, MACD, RSI, and dates remain legible; inspect content rather than exact pixel equality. |

**Done when:** one inspectable chart and its precise numerical provenance are available for the multimodal agent and UI.

## T05 — Vision-based technical assessment and scoring

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T01–T04.

**Implementation**

- Build the technical `create_agent` with the common vision-capable Azure model and structured output. Invoke it only after the dataset, indicators, and PNG are validated.
- Supply actual PNG bytes in a supported image content block, not a local filename or URL inaccessible to the provider. Include ticker, dates, horizon, latest OHLCV/MACD/RSI values, and data-quality limitations.
- Expose a read-only `inspect_technical_series(start_date, end_date)` tool over the frozen run dataset, capped at four calls and 126 rows per call. It cannot fetch a different ticker or execute arbitrary code.
- Require parameter scores and explanations for price structure, MACD, RSI, and volume where supported. Explain conflicting signals; overbought alone is not an automatic bearish score, nor oversold an automatic bullish score.
- Validate any exact prices/indicator values cited in structured observations against the stored series at display precision. Price-level ranges are labeled estimates; do not claim profitable forecasts or add order execution.
- Apply shared weighted scoring and evidence gates. Missing volume may yield 80% coverage; missing MACD/RSI, rejected image input, or chart failure prevents a final score.
- Register the adapter and expose progress for fetching prices, computing indicators, rendering chart, interpreting chart, and validating result.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T05-01 | U | Capture the actual graph's model request: image block contains decodable bytes matching the saved chart hash, alongside correct ticker/dates/numbers. |
| T05-02 | U | Model requests a bounded series slice then returns valid scores: slice is scoped, required image is still present, structured result passes. |
| T05-03 | U | Model tries another ticker, out-of-window dates, excessive rows, or a fifth inspection call: denied/bounded before external work. |
| T05-04 | U | Vision unsupported, missing image, corrupt PNG, or provider image rejection: explicit failure and no silent text-only final score. |
| T05-05 | U | Scores 8/6/4/7: final 6.3; missing volume yields 80% coverage and normalized score; missing mandatory RSI yields insufficient data. |
| T05-06 | U | Claimed latest RSI/price disagrees with stored values, or citations refer to another run: output rejected and bounded repair/failure occurs. |
| T05-07 | U | Mixed MACD/RSI and overbought-uptrend fixtures: result preserves signal disagreement and evidence; no unconditional RSI-to-buy/sell rule is encoded. |
| T05-08 | U/P | Stale dataset or provider outage: stale successful data has a dated limitation/lower confidence; outage has failed status, not a neutral technical score. |

**Done when:** a real multimodal request is required by the execution path and final arithmetic/provenance is enforced outside the model.

## T06 — Technical result and chart view

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T05; common UI available.

**Implementation**

- Add a technical detail renderer showing final/parameter scores, 2–8 week horizon, last completed session, data freshness, latest indicator values, interpretation, confidence, and limitations.
- Show the registered chart with meaningful alt text and an accessible larger-image action. Supply the numerical summary/table as a complementary accessible view.
- Link to run data/indicator provenance where useful; label adjusted prices, missing volume, short history, and stale data.
- Reuse common polling/history and preserve older charts when rerunning; resolve artifacts by selected run ID.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T06-01 | B | Completed fixture: correct chart, latest date, MACD/RSI values, parameter weights, and final score appear together. |
| T06-02 | B | Missing artifact or unsupported vision failure: explicit recovery/error, no broken image presented as successful analysis. |
| T06-03 | B | 59-bar, stale-data, and missing-volume fixtures: correct insufficient/limited states with nulls instead of invented values. |
| T06-04 | B | Switch company/history during a delayed image response: image and numerical data stay associated with the selected run. |
| T06-05 | B | Keyboard, image expansion, mobile width, 200% zoom: chart action and numerical alternative remain usable and labeled. |

**Done when:** users can inspect the same chart the model received and understand its dates, numbers, and limitations.

## T07 — Technical acceptance suite and handoff

**Status:** [See tracker](status.md#technical-agent). **Depends on:** T01–T06.

**Implementation**

- Maintain reviewed bullish, bearish, mixed, flat, split-adjusted, stale, and short-history OHLCV fixtures with independent MACD/RSI expectations.
- Test API → worker → Yahoo adapter fixture → chart → actual graph with fake model → persistence/UI. Never substitute only a mocked final score for the pipeline acceptance test.
- Run live Yahoo retrieval for an approved `.NS` ticker and a real Azure chart-image assessment. Apply the shared three-run live evaluation standard to fixed bullish/bearish/mixed chart fixtures.
- Record dependencies, calculation/render/prompt versions, chart/data hashes, output observations, coverage, and implementation commit. Document unavailable symbols and vision recovery.

| Test ID | Layer | Scenario and expected result |
|---|---|---|
| T07-01 | P/A | Execute representative fixtures end to end: immutable data/chart/indicator provenance, valid model image request, and independently verified final scores. |
| T07-02 | U/P | Split fixture and completed-session boundary fixtures: no false split signal, future/incomplete rows excluded, independent indicator expectations pass. |
| T07-03 | P/B | Restart/recover between chart creation and assessment: stored snapshot/PNG reused consistently and only current lease owner completes. |
| T07-04 | U/P/B | All Txx cases, affected common/provider regressions, frontend build, and coverage checks pass. |
| T07-05 | L | Live Yahoo `.NS` fetch: actual daily OHLCV is nonempty/valid, timestamps and adjustment metadata recorded; provider outage is reported explicitly. |
| T07-06 | L | Real Azure assessment of chart fixtures three times: all requests contain images; cited numbers match data; contradictory visual conclusions are investigated and no unsupported material observations pass. |
| T07-07 | L/B | Run approved company from UI: generated chart is the actual model input and saved result survives refresh/history selection. |

**Done when:** offline numerical and multimodal invariants plus live provider gates pass independently of fundamental/news implementations.
