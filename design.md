# Market Analyst design system

Status: frozen baseline · September 2026

## Direction

A focused enterprise research workspace. Quiet, precise, and compact. Use a dark
navigation rail beside a light working surface. Prioritize company data and actions;
avoid decorative dashboards, large introductions, gradients, and unnecessary cards.

## Application shell

- Desktop: 232px fixed left sidebar, 64px workspace header, flexible main content
  with 40px padding and a maximum width of 1280px.
- Brand: small teal chart mark and “Market Analyst”. Navigation order: Companies
  (Building2), Documents (Files), Agentic Analysis (Workflow).
- Navigation uses icons plus short labels; active links use a muted teal background
  and bright text. The header shows the current workspace location.
- Below 760px: 68px icon sidebar with accessible names/tooltips, 20px content
  padding, wrapping page controls, and horizontally scrollable tables.
- Each page has one h1 and one primary action. Future modules reuse this shell.
  Unimplemented destinations show an honest, concise planned-state message.

## Tokens

Canonical implementation: `frontend/src/styles.css`.

| Token | Value | Purpose |
| --- | --- | --- |
| Canvas | #f5f7f9 | Workspace background |
| Surface | #ffffff | Tables, dialogs, header |
| Navigation | #14252c | Sidebar |
| Text | #172d35 | Main content |
| Muted | #64747c | Secondary content |
| Border | #e2e8eb | Dividers and controls |
| Accent | #087f72 | Primary actions and focus |
| Accent hover | #06675d | Action hover |
| Accent soft | #e9f5f2 | Subtle selection |
| Danger | #bd3434 | Destructive actions and errors |

Use a native sans-serif stack; 14px body, 13px controls and supporting text,
28px/600 page titles, 18px dialog titles. Tickers use monospace. Use a 4px spacing
scale, 8px control radii, 12px surface radii, and 1px borders. Shadows are reserved
for dialogs. Controls are at least 36px tall; table rows approximately 68px.

## Components and language

- Lucide outline icons: 18px, consistent stroke weight. Use icon-only controls for
  familiar row actions (pencil, trash, close), with accessible names and tooltips.
  Primary actions retain icon + text. Never rely on an icon or color alone for errors.
- Tables: compact header, clear column labels, horizontal dividers, subtle hover,
  right-aligned row actions. No decorative metrics or fake example records.
- Search sits inside the table toolbar; record counts are quiet supporting text.
- Add/edit uses a focused modal with visible labels and concise inline errors.
  Use native dialog behavior for focus trapping, Escape, and focus restoration.
- Delete requires a named confirmation dialog. Keep errors in context and preserve
  user input after failed requests. Disable submissions while saving.
- Loading, empty, no-results, and failed-request states are required. Failed reads
  offer Retry. Successful mutations announce a brief message to screen readers.
- Use short labels: “Add company”, “Company name”, “Yahoo Finance ticker”.
  Limit explanatory copy to a useful example or a recovery action.

## Companies contract

Company name and Yahoo Finance ticker are required. Trim names and uppercase
symbols. New or edited tickers accept NSE equity symbols only: a bare symbol gains
`.NS`; `RELIANCE.NS`, `M&M`, and `BAJAJ-AUTO.NS` are examples. Reject other exchange
suffixes, indices, FX syntax, embedded spaces, and canonical symbols over 40
characters. Canonical symbols are unique, including collisions with legacy bare
symbols. Existing global/bare records remain readable; analysis requires an explicit
correction and save. Never merge or silently relabel legacy companies. Format
validation does not verify Yahoo availability. Preserve invalid form input and
announce inline errors with a link to the field. Persist through the API.

## Documents contract

- Documents follows the same heading, panel, table, filter, dialog, empty-state,
  and notification patterns as Companies. Each row shows company, fiscal year,
  filename, ingestion status, upload time, and actions.
- Status uses compact text badges and an ordered vertical pipeline. State is
  conveyed by text and icon as well as color. Failed runs retain their error and
  offer one clear Retry action.
- Document details fill the available workspace without outer page margins.
  Content becomes available as soon as parsing completes, even while later
  ingestion stages continue or fail.
- Content is a two-column, page-synchronized working view. The left pane renders
  one Markdown page with previous/next controls and a direct page-number field at
  the bottom. The right pane shows only chunks assigned to that page, including
  chunk ID, sequence, page, type, token count, heading path, overlap, and content.
  Below 760px the panes stack and scroll independently.
- The document detail tabs are Status, Content, and Search, with keyboard arrow,
  Home, and End navigation. Search has a top form for Query, Chunks (K, default
  10), and Token budget (default 10,000). It searches the current document across
  all pages once ingestion completes.
- Search displays only the latest submitted query's ranked matches, reusing the
  Content chunk metadata and content presentation. Show result count, query, and
  token usage; explain when whole chunks are excluded by the budget. Include
  initial, not-ready, loading, empty, and retry states. Stack controls on mobile.
- Upload uses the standard focused dialog. Company, fiscal year ending, and one
  PDF up to 50 MB are required. Deletion names the report and explains that all
  derived ingestion data is removed.

## Analysis contract

- Agentic Analysis reuses the application shell with one Run analysis action,
  a labeled company selector, and Fundamental, Technical, and News tabs. Tabs
  support Arrow keys, Home, End, and a single Tab stop.
- Keep selection controls in one compact panel. Show textual run status and
  progress in a polite live region, then saved history and the selected result.
  Unavailable agents remain visible with an honest reason and Check availability.
- Poll active runs every two seconds and stop after a terminal state or page exit.
  Ignore responses for superseded company/agent selections. Keep the previous
  successful result visible while a new run queues, executes, or fails.
  Remember the selected company and agent within the browser tab across reloads;
  always retrieve run history from the server.
- Results show the saved company/ticker and assessment time, score, evidence
  coverage, confidence, a generic parameter table, strengths, risks, limitations,
  and evidence IDs/excerpts. Missing scores read “Not scored”. Do not substitute
  zero or a neutral score. Agent tracks may add focused detail renderers here.
- Evidence text renders as plain text. Source links allow HTTP(S) only. Artifact
  download buttons fetch registered IDs through the authenticated API; never
  expose storage paths or embed credentials in URLs.
- Empty companies offer admins Add company; ticker errors offer admins Correct
  ticker. General users receive guidance to contact an administrator instead.
  Failed reads offer Retry. Preserve the selected context after a failed submission.
- Stack and wrap controls on small screens. Parameter tables scroll inside an
  accessible, keyboard-focusable region without widening the page. Use the
  existing colors, type scale, borders, and spacing; no new design tokens.

## Authentication

- Signed-out visitors see a compact Market Analyst sign-in panel with Sign in and
  Sign up controls. Clerk owns the authentication forms and account management.
- Signed-in users access their profile and Sign out through the header user button,
  which remains visible at mobile widths. Clerk uses the existing font and color tokens.
- Mount workspace pages only after session loading and API access verification.
  Show loading, unavailable, and access-pending states with Retry where appropriate.
- Signing out or switching sessions clears mounted workspace state.
- Admins see Companies, Documents, and Agentic Analysis. General users see only
  Agentic Analysis and land there, including when opening a Companies or Documents
  URL. The brand home link follows the user's default page. Roles come from the API.
- Company management, documents, uploads, and document search require admin access
  on the server. Both roles can select companies and run/view analysis and evidence.

## Accessibility and behavior

Semantic navigation, headings, tables, forms, and buttons. Visible keyboard focus,
properly labeled search and icon controls, and live announcements. Respect reduced
motion. Keep hover/focus transitions under 160ms; no decorative animation. Content
must work at mobile widths and 200% zoom. Every future page must reuse these tokens
and patterns; intentional design changes must update this document in the same commit.
