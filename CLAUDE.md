# Project: [PRODUCT_TITLE_TBD]

## Design context

Before changing anything the user sees, read [PRODUCT.md](PRODUCT.md) (strategy: register, users, positioning, anti-references, design principles) and [DESIGN.md](DESIGN.md) (the visual system: color roles, type ladder, elevation, components, do's and don'ts). DESIGN.md wins on visual decisions; PRODUCT.md wins on strategic and voice decisions.

Three rules from DESIGN.md that are violated most often, so they are worth repeating here:
- `text-zinc-500` (`#71717a`) is **prohibited for text** — it fails WCAG AA (4.12:1 computed, 3.85:1 measured in-page). Use `text-zinc-400` (7.75:1) as the muted floor, placeholders included.
- **No `box-shadow` at rest.** Depth comes from the tonal ramp (`zinc-950` ground → `zinc-900` panel → `zinc-800` raised) plus 1px hairline borders. Shadow is permitted only as a focus/active state response.
- **Emerald is the only accent.** Red, amber, sky, and violet are semantic status hues. Never pick a hue for visual variety; a new color requires a new meaning.

## What this is

[PRODUCT_TITLE_TBD] is a chat-driven tool that lowers the barrier to training ML models, aimed at engineers who can code but don't have deep ML expertise. Think "base44 or Replit, but for training a model" instead of "for building an app."

The user describes their data and what they want to do with it in plain language. The system then:
1. Interprets the problem (classification, regression, forecasting, sequence tagging, etc.)
2. Selects an appropriate methodology from a curated, predefined set of ML approaches — not an unbounded search space
3. Assembles the data pipeline, trains the model, and reports results back in a way a non-ML-specialist can act on

## Why this is different from existing AutoML

Existing AutoML platforms (Google AutoML/Vertex, Azure AutoML, H2O, DataRobot, PyCaret, AutoGluon) already automate preprocessing, feature engineering, model selection, and hyperparameter tuning — mostly for tabular classification/regression. Two gaps [PRODUCT_TITLE_TBD] is meant to target:

- **Judgment, not just search.** Most AutoML tools require you to already know the problem framing (pick a task type, pick a target column). [PRODUCT_TITLE_TBD]'s job is to help figure out *which* framing and methodology fits the described data and goal — closer to how a senior ML engineer would triage a new problem than to a hyperparameter grid search.
- **Full pipeline, not just the training step.** AutoML demos are strong on "upload CSV, get accuracy score." They're weak on the parts that actually block engineers in practice: turning a training-time feature snapshot into a real-time feature pipeline, setting up drift monitoring, and making retraining a non-manual process. [PRODUCT_TITLE_TBD] should treat these as first-class, not afterthoughts.

## Target user

Engineers who can write code and stand up infrastructure, but find data pipelines, model architecture selection, and parameter tuning to be the actual bottleneck. Not aimed at non-technical users — the value is in removing ML-specific expertise requirements, not general coding ability.

## Core design principles

- **Predefined methodology set, not full autonomy.** The system chooses from a curated library of known-good approaches rather than freely inventing architectures. This keeps behavior predictable, debuggable, and explainable — critical for engineer trust.
- **Show the reasoning.** When [PRODUCT_TITLE_TBD] picks a methodology, it should explain *why* (data characteristics, size, task type) so the user can sanity-check or override it — similar to Databricks AutoML's "glass box" approach of generating editable, inspectable code rather than a black-box endpoint.
- **Pipeline-aware from the start.** Feature engineering steps should be defined in a way that's portable to production, not just a one-off notebook transformation.
- **Conversational interface, real infrastructure underneath.** The chat window is the UX layer; underneath, it's provisioning real training jobs, real pipelines, and real deployable artifacts — not a toy demo.

## Open questions / things to figure out

- How wide should the "predefined methodologies" library be at launch? (Start narrow — e.g. tabular classification/regression + one or two other task types — and expand.)
- How much should the system ask clarifying questions vs. just proceed with a reasonable default and explain its choice?
- What does "done" look like for v1 — a trained model + eval report, or a deployed endpoint + monitoring?
- Build vs. wrap: how much of the actual training/tuning logic should be custom vs. built on top of existing libraries (AutoGluon, H2O, PyCaret) with an agentic selection/orchestration layer on top?

## Non-goals (for now)

- Not trying to compete with DataRobot/Vertex on enterprise governance, compliance, or explainability tooling.
- Not targeting non-technical users — this is not a "no-code for business analysts" product.
- Not aiming to support arbitrary novel architectures — the constrained methodology set is a feature, not a limitation to remove.
