# Manufacturing Control Tower frontend — design QA

## Visual truth

Approved references:

- `../docs/design/manufacturing-control-tower-frontend/login.png`
- `../docs/design/manufacturing-control-tower-frontend/welcome.png`
- `../docs/design/manufacturing-control-tower-frontend/analyzing.png`
- `../docs/design/manufacturing-control-tower-frontend/completed-chat.png`
- `../docs/design/manufacturing-control-tower-frontend/error.png`

The references and the live implementation were inspected directly. Implementation captures were taken in the Codex in-app browser; that browser exposes the images for visual review but does not provide persistent screenshot file paths.

## Comparison history

| Pass | Viewport / state | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | 1488 × 1058 / login | Layout was readable but the decorative data motif was intentionally quieter than the concept. | Accepted as a compact implementation; hierarchy, fields, brand, demo notice, and date match the approved direction. |
| 1 | 1488 × 1058 / welcome | Window scroll could retain the login position and clip the application header. | Locked document overflow and moved scrolling into the conversation region. |
| 1 | 1488 × 1058 / analyzing | Bottom composer could sit above the viewport edge on long content. | Made the app frame a fixed-height flex layout with an independently scrolling conversation. |
| 1 | 390 × 844 / welcome | Composer textarea exposed native scroll controls. | Hid textarea overflow while retaining its bounded multiline height. |
| 1 | 390 × 844 / navigation | Immediate capture showed only the backdrop during the drawer transition. | Re-captured after the transition; drawer, close control, history, and account row were all visible and usable. |
| 2 | 1488 × 1058 / error | Programmatic error-heading focus used a full-width browser outline. | Constrained the heading and replaced it with a compact, visible focus ring. |
| 2 | 1488 × 1058 / completed | Run-again lost its source question after a successful response. | Preserved the last submitted question and added a reducer regression test. |

## Interaction validation

- Invalid credentials show inline feedback; the supplied demo credentials sign in.
- Refresh returns to the login screen and clears in-memory state.
- All four supplied recommendations render with exact wording.
- Recommendation and typed-question submission work; Enter submits, Shift+Enter remains available for multiline input, and empty/duplicate submissions are guarded in state.
- Three chats were created and switched during QA; messages and Foundry identifiers remained isolated per chat.
- `New analysis` opens a blank chat without deleting prior in-memory history.
- The nine thinking messages rotate every four seconds with text-only pulse treatment and no loader bar.
- A real Pune recommendation completed through the Azure Function after the long-running analyzing state.
- Markdown headings, lists, emphasis, links, and a wide GFM table rendered without raw HTML injection; the table stayed within the conversation column.
- Copy displayed its confirmation state. Run-again re-entered analyzing with the completed question.
- With the local proxy deliberately stopped, the submitted question remained visible and the safe retry state exposed no URL, status, stack, key, or backend response body.
- Restoring the proxy allowed real requests to complete again.
- Desktop sidebar and mobile drawer were exercised by clicking their controls.
- Reduced-motion CSS removes the repeating composer rotation, thinking pulse, and drawer translation.
- Browser console query after the real completed flow returned no warnings or errors.

## Result

Final result: passed. `npm test`, `npm run build`, and `npm run test:sites` all completed successfully on 28 Sep 2026.
