# Manufacturing Control Tower Frontend Design

Date: 2026-09-28  
Status: Approved visual direction; implementation plan pending

## 1. Purpose

Build a polished demo frontend for the existing `manufacturing-control-tower-agent`. The application helps a manufacturing operations manager ask analytical questions about customer commitments, understand the evidence behind risk, and review proposed recovery actions.

The frontend replaces the current Power Apps chat surface. It does not change the Foundry agent, its data, or the Azure Function.

Success means a user can:

1. pass through a simple demo login;
2. start an analysis from a concise welcome screen;
3. use recommended manufacturing questions or write a custom question;
4. follow multiple temporary chats from an in-memory history sidebar;
5. understand that a long analysis is still running;
6. read Markdown, lists, headings, code blocks, and tables comfortably;
7. retry a failed request without losing the question; and
8. see the static snapshot and human-approval boundaries throughout the experience.

## 2. Scope

### Included

- React desktop web application, responsive down to mobile widths.
- Hardcoded demo login backed by frontend environment values.
- Welcome, analyzing, completed-chat, and recoverable-error states.
- In-memory conversations and chat history.
- Recommended questions.
- Existing Azure Function `/api/chat` integration.
- Multi-turn state through `response_id` and `agent_session_id`.
- Markdown and GitHub-flavored table rendering.

### Excluded

- Real authentication or authorization.
- Database or durable chat persistence.
- Streaming responses.
- File upload, voice, sharing, collaboration, analytics, or approval execution.
- Changes to the Foundry agent or Azure Function contract.
- A dashboard, KPI grid, or direct operational controls.

## 3. Architecture Boundary

```text
React frontend
    |
    | POST /api/chat
    v
Existing Azure Function
    |
    | Managed Identity
    v
Existing Microsoft Foundry agent
```

The frontend follows [`frontend-chat-integration-contract.md`](../../frontend-chat-integration-contract.md). It sends `message`, `previous_response_id`, and `agent_session_id`, then stores the returned identifiers in the active in-memory chat.

The frontend renders the response's raw `answer` Markdown. `answer_html` remains a Power Apps compatibility field and is not injected into the React DOM.

## 4. Approved Visual Direction

The chosen direction is a luminous enterprise workspace: true white and pale cool-gray surfaces, navy typography, cobalt actions, restrained cyan/violet accents, fine contour-line artwork, and one editorial serif headline paired with compact sans-serif controls.

Reference screens:

- [Welcome](../../design/manufacturing-control-tower-frontend/welcome.png)
- [Login](../../design/manufacturing-control-tower-frontend/login.png)
- [Analyzing](../../design/manufacturing-control-tower-frontend/analyzing.png)
- [Completed chat](../../design/manufacturing-control-tower-frontend/completed-chat.png)
- [Recoverable error](../../design/manufacturing-control-tower-frontend/error.png)

The images define composition and visual character. The sizing rules below override any oversized elements in the mockups.

### Visual thesis

A calm, precise analytical workspace whose intelligence is conveyed through typography, spacing, and a restrained signal glow rather than dashboard density or decorative effects.

### Interaction thesis

- The welcome composer is the central action and docks to the bottom after submission.
- The thinking state communicates activity through a small pulsating status line, not a progress bar or theatrical animation.
- A faint rotating cyan-to-violet edge glow gives the composer a consistent AI signature without overwhelming the interface.

## 5. Compact Layout System

The interface must not use oversized AI-generated controls. Desktop sizing targets:

| Element | Target |
|---|---:|
| Sidebar width | 240px; 220px at narrower desktop widths |
| Main page horizontal padding | 32px–48px |
| Conversation column | 760px–840px maximum |
| Welcome content width | 880px maximum |
| New analysis button | 40px high |
| Sidebar history row | 36px high |
| Welcome composer | 56px high |
| Docked composer | 52px high |
| Standard button | 38px–40px high |
| User message bubble | 65% of conversation width maximum |
| User bubble padding | 10px 14px |
| Panel/control radius | 10px–14px |
| Composer radius | 16px–18px |

Use an 8px spacing base with 4px adjustments. Prefer 8, 12, 16, 24, 32, and 48px gaps. Avoid large empty bands created only for visual drama.

### Type scale

| Role | Size / line height |
|---|---|
| Welcome display | 48–52px / 1.08 desktop; 34–38px mobile |
| Page title | 22px / 1.25 |
| Section heading | 16–18px / 1.35 |
| Chat body | 15px / 1.65 |
| Controls and sidebar | 14px / 1.4 |
| Metadata | 12–13px / 1.45 |
| Thinking status | 14–15px / 1.4 |

Use `ui-serif, Georgia, serif` for the welcome display and `Inter, "Segoe UI", sans-serif` for application UI. Do not add another font family.

## 6. Design Tokens

Initial implementation values:

| Token | Value | Use |
|---|---|---|
| `--background` | `#FFFFFF` | Main canvas |
| `--sidebar` | `#F7F9FD` | Navigation surface |
| `--text` | `#0A1733` | Primary text |
| `--text-muted` | `#68779C` | Metadata and supporting text |
| `--border` | `#DCE5F4` | Dividers and control outlines |
| `--accent` | `#1768F2` | Primary action |
| `--accent-cyan` | `#31C5F4` | Glow detail |
| `--accent-violet` | `#7765F8` | Glow detail |
| `--accent-soft` | `#EDF4FF` | Active sidebar row |
| `--error` | `#C62C3A` | Error icon and heading only |
| `--shadow` | `0 8px 28px rgb(23 104 242 / 0.10)` | Focused primary controls |

Color values may be adjusted slightly during browser fidelity work, but the background stays true white and the system remains cool rather than cream or beige.

## 7. Application States

### 7.1 Demo login

- Shows ScatterPie and Manufacturing Control Tower branding.
- Contains work-email and password inputs and one `Sign in` action.
- Credentials come from frontend environment values and are checked only in browser memory.
- Invalid credentials produce a compact inline message below the relevant field.
- `Demo access only` and `Static manufacturing snapshot · 15 Sep 2026` remain visible.
- Successful login stores only an in-memory authenticated flag. Refreshing returns to login.

### 7.2 Welcome

- Sidebar shows `New analysis`, temporary chat history, and user identity.
- Main content shows `Good morning, Abhishek.` and `What should we analyze today?`.
- Centered composer is the primary action.
- `Suggested analyses` appears immediately below the composer; there is no `Available context` section.
- Recommended questions:
  - How exposed are we over the next two weeks?
  - Which Pune orders should planners chase first?
  - What is the lowest-cost recovery plan?
  - How much revenue is blocked by customer holds?
- Selecting a recommendation places and submits that exact question.

### 7.3 Analyzing

- The submitted question appears in a compact, right-aligned cobalt bubble.
- The composer docks at the bottom and remains visually compact.
- The assistant area contains a 24px mark and one 14–15px status line.
- Remove the mockup's progress bar completely.
- The status text gently pulses between 65% and 100% opacity. A three-dot indicator may pulse beside it, but it must stay visually smaller than the text.
- Status changes every 3.5–5 seconds and loops until the request completes:
  1. Reviewing order commitments…
  2. Checking late-order risk signals…
  3. Reviewing inventory and reservations…
  4. Tracing production and quality constraints…
  5. Comparing recovery options…
  6. Estimating service and cost impact…
  7. Preparing an evidence-backed response…
- These are presentation messages, not claims about actual internal reasoning.
- A muted `This can take up to 90 seconds.` label may appear beneath the status at 12px.

### 7.4 Completed chat

- User messages remain right aligned in a cobalt bubble.
- Assistant messages have no containing bubble or card.
- Assistant content uses a readable Markdown column with clear heading hierarchy, 15px body text, 1.65 line height, and 12–16px paragraph spacing.
- Lists use compact indentation and 6–8px item gaps.
- Tables have a subtle header tint, 40px minimum rows, hairline borders, and horizontal overflow on narrow screens.
- Code blocks use a cool-gray surface and horizontal overflow.
- Copy and retry are small icon buttons beneath the response.
- The fixed composer remains available for follow-ups.

### 7.5 Recoverable error

- Preserve the user question.
- Show a restrained inline error icon and `We couldn’t complete that analysis.`
- Show `Try again` as the primary action and `Start a new analysis` as a secondary action.
- Do not expose raw Function error text, status codes, endpoint names, or stack traces.
- Retrying resends the same question with the active chat's current conversation identifiers.

## 8. Sidebar and In-Memory Chat History

Each chat stores:

```text
id
title
messages
responseId
agentSessionId
status
```

- `New analysis` creates a blank active chat and clears the Foundry identifiers for that chat only.
- The title is the first user question, truncated to approximately 32 characters.
- Switching chats restores messages and that chat's Foundry identifiers.
- Histories exist only for the current page lifetime and disappear on refresh.
- Do not show timestamps unless they are generated from the current browser session.
- On mobile, the sidebar becomes a dismissible drawer.

## 9. Composer

The welcome and docked composers are the same component in two layout variants.

- Enter submits; Shift+Enter inserts a newline.
- Empty or whitespace-only questions cannot be submitted.
- During a request, prevent duplicate submission.
- Use a 36px circular send control inside the composer.
- Focus must remain clearly visible without a heavy outline.

### Rotating glow

Use a masked 1px pseudo-element around the composer with a low-opacity conic gradient from cyan to cobalt to violet. Rotate it slowly over 5–7 seconds. Blur may extend no more than 6–8px beyond the control and should remain faint on white.

The effect pauses or becomes a static border under `prefers-reduced-motion`. It must not change layout, reduce text contrast, or resemble a loading progress ring.

## 10. Motion

- Welcome content: short 180–240ms opacity/translate entrance.
- Composer docking: 240–320ms ease-out position/layout transition.
- Thinking status: 1.4–1.8s opacity pulse.
- Composer edge glow: 5–7s linear rotation.
- Sidebar selection and hover: 120–160ms color transition.
- Respect `prefers-reduced-motion` by removing translation, rotation, and repeated pulsing.

No animation should delay input or response rendering.

## 11. Responsive Behavior

- Desktop `>= 1024px`: persistent sidebar and centered conversation column.
- Tablet `768–1023px`: 220px sidebar and reduced main padding.
- Mobile `< 768px`: sidebar drawer, 16px page padding, full-width composer, 34–38px welcome headline, single-column recommendations, and tables scrolling within the message column.
- The docked composer must not cover the last response; reserve bottom content padding equal to its full height plus 24px.

## 12. Accessibility

- Semantic form labels and chat regions.
- Keyboard-operable sidebar, recommendations, message actions, retry, and composer.
- Visible focus indicators.
- Minimum 44px pointer target where practical; compact desktop rows may be 36–40px when adjacent targets remain separated.
- Sufficient text and control contrast.
- Loading state announced through a polite live region without announcing every pulse.
- Completed response announced once when inserted.
- Error state receives focus at its heading.

## 13. Content and Trust Boundaries

- Always display `Snapshot · 15 Sep 2026` or the equivalent static-snapshot notice.
- Never imply data is live or connected in real time.
- Keep facts, predictions, inferred causes, and proposed actions visually readable but do not invent structured labels that the agent did not return.
- Preserve Markdown wording from the agent rather than rewriting numerical results in the frontend.
- Keep `Recommendations require human approval` visible in the application footer.
- Do not provide UI controls that appear to execute holds, freight bookings, production changes, or other controlled actions.

## 14. Verification and Acceptance

Before handoff:

1. verify login success and invalid-credential behavior;
2. create, switch, and clear multiple in-memory chats;
3. verify each chat retains its own Foundry identifiers;
4. submit a recommended and a typed question;
5. verify the status loop runs without a loader bar and stops on completion/error;
6. verify Markdown headings, lists, tables, and code blocks;
7. verify retry resends the failed question;
8. verify new analysis clears only the active conversation;
9. inspect desktop and mobile layouts;
10. compare browser screenshots with the five approved references;
11. confirm component sizes match the compact sizing table; and
12. confirm the rotating composer glow is subtle and reduced-motion safe.

## 15. Deliberate Simplifications

- Browser memory replaces persistence.
- Hardcoded credentials replace authentication.
- Non-streaming response handling remains unchanged.
- Preconfigured status text replaces server-side progress events.
- One app shell and one reusable composer cover all chat states.

Add persistence, Entra authentication, or streaming only if the demo becomes a maintained application.
