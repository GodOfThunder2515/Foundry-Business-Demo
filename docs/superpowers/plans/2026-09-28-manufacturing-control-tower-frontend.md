# Manufacturing Control Tower Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved compact React chat frontend for the existing manufacturing-control-tower Azure Function and Foundry agent.

**Architecture:** A React 19/Vite 6 application lives under `frontend/`. Its browser state owns demo login and temporary conversations; a Vite development proxy reads `FUNCTION_URL` and `FUNCTION_KEY` from the ignored root `.env` and forwards `/api/chat` without exposing the key to client JavaScript.

**Tech Stack:** React 19, Vite 6, react-markdown, remark-gfm, Phosphor icons, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-28-manufacturing-control-tower-frontend-design.md`

## Global Constraints

- Do not change the Foundry agent, Azure Function, or `/api/chat` contract.
- Keep login and conversations in memory only; refresh returns to login.
- Render raw `answer` Markdown and never inject `answer_html`.
- Keep the static snapshot and human-approval notices visible.
- Match the five approved images under `docs/design/manufacturing-control-tower-frontend/`.
- Keep controls compact and respect `prefers-reduced-motion`.

## Review Focus

- A response finishing after the user switches chats must update its originating chat only.
- Failed requests must preserve the question and never expose raw backend errors.
- New chats must begin with empty Foundry identifiers while existing chats retain theirs.
- The fixed composer must not cover the final response at desktop or mobile widths.
- Function credentials must remain outside the browser bundle.

---

### Task 1: Scaffold and test the state/API core

**Files:** `frontend/`, `frontend/src/chat.js`, `frontend/tests/chat.test.mjs`, `frontend/vite.config.mjs`

- [ ] Bootstrap the Product Design web prototype and install the approved dependencies.
- [ ] Write and run failing Node tests for login validation, message validation, per-chat state, late responses, retry state, and API request/response mapping.
- [ ] Implement the minimal pure state/API helpers and root-env Vite proxy needed to pass.
- [ ] Run `npm test` and commit.

### Task 2: Implement login, welcome, and conversation UI

**Files:** `frontend/src/App.jsx`, `frontend/src/styles.css`, `frontend/public/sp-logo.png`

- [ ] Add the supplied logo asset and approved design tokens.
- [ ] Implement hardcoded demo login, responsive app shell, sidebar, welcome composer, and exact suggested questions.
- [ ] Implement chat switching, new analysis, docked composer, nine-message thinking loop, Markdown response, error/retry, copy, and mobile drawer.
- [ ] Run tests and build, then commit.

### Task 3: Browser integration and responsive validation

**Files:** frontend implementation files only when browser findings require fixes.

- [ ] Start the local Vite server and use Browser/IAB for invalid login, valid login, recommendations, typed input, history switching, mobile drawer, and live Function request.
- [ ] Inspect analyzing, completed, and failure/retry states; check console output and reduced motion.
- [ ] Fix every functional or visual defect found, rerunning `npm test` and `npm run build` after fixes.
- [ ] Commit verified browser fixes.

### Task 4: Formal design QA and handoff

**Files:** `frontend/design-qa.md`, `frontend/qa/`

- [ ] Capture all five states at the reference viewport plus a mobile viewport.
- [ ] Compare references and captures together with image inspection; fix P0/P1/P2 mismatches.
- [ ] Record source paths, captures, viewports, comparisons, interactions, and `final result: passed` in `design-qa.md`.
- [ ] Run `npm test`, `npm run build`, and `npm run test:sites`; keep the verified preview running and commit.
