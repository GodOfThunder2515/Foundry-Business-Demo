# Manufacturing Control Tower frontend — design QA

## Visual truth

Approved references:

- `../docs/design/manufacturing-control-tower-frontend/login.png`
- `../docs/design/manufacturing-control-tower-frontend/welcome.png`
- `../docs/design/manufacturing-control-tower-frontend/analyzing.png`
- `../docs/design/manufacturing-control-tower-frontend/completed-chat.png`
- `../docs/design/manufacturing-control-tower-frontend/error.png`
- `C:/Users/ABHISH~1.BHO/AppData/Local/Temp/codex-clipboard-e24d97c3-5c17-4318-b527-b9a3997041df.png` (requested completed-chat table treatment)
- `C:/Users/ABHISH~1.BHO/AppData/Local/Temp/codex-clipboard-9e36a23f-6ce5-4096-a608-2c5b3fd01466.png` (requested copyright treatment)

The references and the live implementation were inspected directly. Implementation captures were taken in the Codex in-app browser; that browser exposes the images for visual review but does not provide persistent screenshot file paths.

## Comparison history

| Pass | Viewport / state | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | 1488 × 1058 / login | Layout was readable but the decorative data motif was quieter than the concept. | Superseded by pass 3 after user review. |
| 1 | 1488 × 1058 / welcome | Window scroll could retain the login position and clip the application header. | Locked document overflow and moved scrolling into the conversation region. |
| 1 | 1488 × 1058 / analyzing | Bottom composer could sit above the viewport edge on long content. | Made the app frame a fixed-height flex layout with an independently scrolling conversation. |
| 1 | 390 × 844 / welcome | Composer textarea exposed native scroll controls. | Hid textarea overflow while retaining its bounded multiline height. |
| 1 | 390 × 844 / navigation | Immediate capture showed only the backdrop during the drawer transition. | Re-captured after the transition; drawer, close control, history, and account row were all visible and usable. |
| 2 | 1488 × 1058 / error | Programmatic error-heading focus used a full-width browser outline. | Constrained the heading and replaced it with a compact, visible focus ring. |
| 2 | 1488 × 1058 / completed | Run-again lost its source question after a successful response. | Preserved the last submitted question and added a reducer regression test. |
| 3 | 1488 × 1058 / login and welcome | The approved contour artwork was too faint and most of its transparent canvas sat outside the visible composition. | Increased contrast and opacity, enlarged the source asset, and repositioned its visible contours to match the reference's top-right sweep. |
| 3 | 1488 × 1058 / analyzing | The large welcome artwork needed to recede after a question was asked. | Added an 800 ms scale-and-translate transition into the top-right, retaining enough opacity for continuity without competing with the conversation. |
| 3 | 390 × 844 / login | The desktop crop did not translate cleanly to the narrow viewport. | Added a dedicated mobile crop and lower mobile intensity; no content or controls are obscured. |
| 4 | 1488 × 1058 / welcome | Sidebar still used the former studio subtitle and the footer used the earlier synthetic-snapshot notice. | Added the supplied Azure Foundry mark and compact “Powered by Azure Foundry” lockup in the sidebar; replaced the earlier notice with the supplied copyright treatment. |
| 4 | 1488 × 1058 / completed | The table relied on page scrolling for long results. | Bounded the Markdown table to 420 px / 52 vh, enabled two-axis overflow, and kept column headers sticky. Measured 418 × 808 px viewport against 700 × 808 px content. |
| 4 | 390 × 844 / completed | Wide tables needed an explicit horizontal path without clipping the composer or footer. | Confirmed a 326 × 397 px table viewport against 610 × 1129 px content, with both native scrollbars visible and the composer/footer unobscured. |

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
- Completed-response tables expose native horizontal and vertical scrolling, sticky headings, and a keyboard-focusable labeled region.
- Copy displayed its confirmation state. Run-again re-entered analyzing with the completed question.
- With the local proxy deliberately stopped, the submitted question remained visible and the safe retry state exposed no URL, status, stack, key, or backend response body.
- Restoring the proxy allowed real requests to complete again.
- Desktop sidebar and mobile drawer were exercised by clicking their controls.
- Reduced-motion CSS removes the repeating composer rotation, thinking pulse, and drawer translation.
- The decorative artwork's slow 16-second drift was confirmed from changing computed positions; the chat-state scale-and-translate was confirmed after a real recommendation submission.
- Reduced-motion CSS also collapses the artwork drift to a static position.
- Browser console query after the real completed flow returned no warnings or errors.

## Result

Final result: passed. `npm test`, `npm run build`, and `npm run test:sites` all completed successfully on 28 Sep 2026.
