---
target: frontend/src/components/Workspace.tsx
total_score: 18
p0_count: 2
p1_count: 3
timestamp: 2026-07-22T15-40-17Z
slug: frontend-src-components-workspace-tsx
---
Method: dual-agent (A: design review · B: detector + browser evidence), both Sonnet, isolated and parallel.

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Training/SSE status is genuinely good; but which run is *deployed* is invisible in the run list — discoverable only by selecting a run and scrolling. |
| 2 | Match System / Real World | 2 | The live deployment is named `classification.lightgbm` while serving a Logistic Regression run. The name is a stale promotion artifact that now misstates what is running. |
| 3 | User Control and Freedom | 2 | No undo on promote/deploy/retrain. Dataset "Replace" is one-way with no confirmation. |
| 4 | Consistency and Standards | 1 | Promote exists as two different UIs (Workspace one-click button vs DeploymentCard dropdown), sometimes both on screen. Plus two parallel color vocabularies and 19 off-ladder font sizes. |
| 5 | Error Prevention | 2 | Deploy, promote, and dataset-replace all fire immediately on click. No confirmation before swapping the model serving traffic. |
| 6 | Recognition Rather Than Recall | 2 | "Selected vs recommended vs deployed" must be inferred from a ring, a badge, and a card below the fold. Nothing is plainly labeled "deployed". |
| 7 | Flexibility and Efficiency | 1 | No keyboard shortcuts. Three file-upload controls are entirely keyboard-unreachable. No bulk actions. |
| 8 | Aesthetic and Minimalist Design | 1 | 16 distinct action controls on one view at near-identical visual weight; no Headline step anywhere to rank regions. |
| 9 | Error Recovery | 2 | Errors surface inline (good) but are raw backend `detail` strings with no suggested next step. |
| 10 | Help and Documentation | 2 | The chat rail carries the "why" well, but the workspace itself shows ROC-AUC, Brier, calibration, stacking bare with no inline glossing. |
| **Total** | | **18/40** | **Poor — major UX work needed** |

Note: Assessment A reported 19/40; its individual scores sum to 18. Corrected here.

## Anti-Patterns Verdict

**LLM assessment.** Not classic AI slop. No gradient text, no glassmorphism, no sparkle iconography; the palette and flat hairline-bordered surfaces show real intent and mostly honor the Instrument Panel north star. It fails the *product-register* test instead: a Linear-fluent user pauses repeatedly, because this is strangeness-by-accretion rather than by decoration. Every card is the same weight (`rounded-xl border border-zinc-700 bg-zinc-900/80`) stacked in one column, and the codebase contains zero uses of the Headline step. Section labels "Data" and "Model" are rendered at the *smallest* step on the ladder.

**Deterministic scan.** `detect.mjs` over `frontend/src`: exit 2, **23 findings**.
- `design-system-font-size` (19): arbitrary `text-[10px]` / `text-[11px]` across DeploymentCard (6), ReportCard (5), TournamentComparisonCard (2), Workspace (2), PlanCard (2), ComparisonCard (1), ProfileCard (1). All sit *below* the 12px Label floor.
- `gray-on-color` (3): DeploymentCard:391, PredictionCard:104, PredictionCard:120.
- `design-system-color` (1): ReportCard:153.

**Live overlay.** Injection succeeded on the tournament fixture; the in-page detector reported low-contrast, gray-on-color, tiny-text, cramped-padding, and a skipped heading (`h2` → `h4`, no `h3`).

**Measured accessibility evidence:**
- **14 of 24 interactive elements (58%) have no visible focus style** when focused.
- Three contrast pairs below AA: `rgb(212,212,216)` on `#3987e5` at **2.46:1**; `#ffffff` on `#3987e5` at **3.64:1**; `rgb(109,109,109)` on `zinc-950` at **3.85:1** across 13 elements.

**Confirmed false positive:** `overused-font` (Geist at 83% of text). That is a brand-register rule misfiring on a product surface; product register explicitly endorses one family across the UI. Dismissed.

**Corrected:** `design-system-color` on ReportCard:153 was flagged by Assessment B as a *possible* false positive. It is not. It is live text color on the confusion-matrix cell and is the same element measured failing at 3.64:1.

## Overall Impression

The reasoning layer of this product is genuinely good and the visual foundation is sound. The problem is entirely one of **rank**: nothing on this surface outranks anything else. Sixteen action controls, ten card types, and a six-signal navigation pill all render at near-identical weight, so the user's eye has no entry point. The single biggest opportunity is not new features or new styling — it is establishing hierarchy and making "what is actually live" the anchor the Model region is built around.

## What's Working

1. **The glass-box reasoning genuinely delivers the strategic promise.** `plan.reasoning`, TournamentCard's "why this tournament," and the assistant's honest commentary when a user overrides a recommendation ("this is a step down on pure performance") are specific and never assert a score without a mechanism.
2. **The Diagnostics section is senior-engineer-grade.** Leakage-ratio callouts, per-segment worst-case tables, and a calibration reliability plot are exactly the "is this evaluation honest" scrutiny most AutoML stops short of.
3. **The status vocabulary is disciplined.** `STATUS_DOT` / `STATUS_LABELS` are centralized and the semantic-hue mapping (red=fail, amber=warn, sky=info, violet=tournament) holds consistently.

## Priority Issues

**[P0] The deployed model is the hardest fact on the page to find, and can silently contradict the recommendation.**
Nothing in the run list indicates which run is live. On the fixture, the deployed run (Logistic Regression) differs from the recommended run (Random Forest) and the interface never says so. This is the highest-stakes fact in a product whose promise is transparency, and PRODUCT.md states the rule being broken: "When a state is ambiguous or two states disagree, resolve it in the interface."
*Fix:* put a LIVE state on the pill using the existing Status Dot primitive, and render a reconciling banner when deployed differs from recommended.
*Command:* `/impeccable clarify`

**[P0] The run pill carries six signals; the Headline step that exists to fix this is never used.**
Status dot + label + target + version + tournament stripe + recommendation badge, against the design system's explicit two-signal ceiling. Meanwhile region headers use 12px Label type.
*Fix:* reduce the pill to dot + label + one most-relevant state; move version/target to the selected detail; introduce real 20px Headlines for "Data" and "Model".
*Command:* `/impeccable layout`

**[P1] An entire undocumented second palette exists for data visualization.**
`SEQ_HUE`/`SERVED_HUE`/`PRED_HUE` = `#3987e5`, `GOOD` = `#0ca30c`, `BAD` = `#e66767`, hardcoded across ReportCard, DeploymentCard, ComparisonCard, PredictionCard. These duplicate roles the documented palette already owns (sky, emerald, red) with off-system values, and they are the source of the two worst contrast failures. The confusion-matrix cell switches text color at a hardcoded `alpha > 0.55` threshold, which fails at mid-ramp in both directions.
*Fix:* map the chart hues onto the documented tokens and replace the binary alpha threshold with a luminance-derived text color.
*Command:* `/impeccable colorize`

**[P1] Three file-upload controls are keyboard-inoperable.**
"Add dataset", "Update", and "Upload CSV to score" are `<label>` wrappers around `<input type="file" className="hidden">`. Tailwind `hidden` is `display:none`, which removes them from tab order entirely. A keyboard-only user cannot upload anything.
*Fix:* make the label focusable and Enter/Space-operable, or use a real button that programmatically clicks the input.
*Command:* `/impeccable harden`

**[P1] Focus states are missing on 58% of interactive elements, measured.**
14 of 24, including every run pill, "Enable deployment", "Copy", both textareas, and the select.
*Fix:* apply the documented two-ring focus treatment globally.
*Command:* `/impeccable harden`

**[P2] Promote is two different UIs for one action.**
A one-click "Promote to live deployment (v#)" in Workspace and a dropdown-driven "Promote" in DeploymentCard, sometimes both visible in one scroll.
*Fix:* collapse to one; if the dropdown's "promote a run I am not viewing" case is worth keeping, label it as that distinct case.
*Command:* `/impeccable clarify`

## Persona Red Flags

**Alex (power user / ML practitioner, the secondary audience):** No keyboard shortcuts for run switching, retrain, or predict. The pill list is mouse-only, with no arrow-key navigation. All three upload paths are keyboard-unreachable, which is disqualifying for a keyboard-driven user. Must scroll to find whichever of the two promote UIs applies.

**Sam (accessibility-dependent):** 13 elements of muted body text measured at 3.85:1. Inputs use `outline-none focus:border-emerald-600`, replacing the native outline with only a border-color shift; Workspace's own buttons declare no focus styling at all. The `h2` → `h4` jump breaks heading navigation. The icon-only `◉` and `×` buttons announce as their glyph, not their function.

**Jordan (project-specific: the engineer who can code but has no deep ML background — PRODUCT.md's primary user):** Arrives having described their data in plain language and is handed ROC-AUC, PR-AUC, stacking, backtest, calibration, and Brier score bare in the workspace cards. The chat rail explains these well, but it is a 380px sidebar competing for the same screen. A user who reads the workspace instead of the chat gets an unglossed instrument panel — the opposite of "explaining unfamiliar steps without condescending."

## Minor Observations

- The deployment name surfaces raw internal naming (`classification.lightgbm`) with no indication it is renameable; if it is not, the stale-name problem recurs on every promotion.
- "Deploy this model" only renders when the project has zero deployments, and "Promote to live deployment" only when target/task match. A mismatched second run gets neither button and no explanation.
- `cramped-padding` on a bordered container: children sit flush against the border with no inset.
- `extractErrorDetail` is duplicated verbatim in three files.
- The double-logged console output is React StrictMode's dev double-mount, not two scans. Benign.

## Questions to Consider

- If "what is serving traffic right now" is the highest-stakes fact this product owns, why is it the hardest one to find?
- What would the Model region look like if it were built around "one model is live, here is how it compares to what is recommended" instead of a chronological stack of every run's cards?
- Is the six-signal pill actually serving practitioner density, or standing in for a run table that was never built?
- The design system names the Headline step as the sanctioned fix for a flat scroll, and this component never uses it. Was it written before the rule, or is it aware of the rule and unapplied?
