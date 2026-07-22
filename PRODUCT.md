# Product

## Register

product

## Platform

web

## Users

The primary user is an engineer who can write code and stand up infrastructure but does not have deep ML expertise. Their bottleneck is not general engineering ability; it is the ML-specific work: framing the problem, building data pipelines, choosing an architecture, and tuning. They arrive with data and a goal stated in plain language and need the system to handle the ML judgment while leaving them in control.

A secondary audience is ML engineers and data scientists who already know the field and use the tool to move faster or to sanity-check the system's reasoning. The interface should let this group go deeper and inspect the details without forcing that density on the primary user.

## Product Purpose

Model Builder (the name is provisional) is a chat-driven tool for training ML models. A user describes their data and what they want to do with it; the system interprets the problem, selects an appropriate methodology from a curated set of known-good approaches, assembles the pipeline, trains the model, and reports results a non-specialist can act on.

Success is the whole loop cohering as one legible journey: describe, train, inspect, deploy, monitor, retrain. The value is not any single step but the fact that these steps connect and stay understandable end to end. A user should always know where they are in that loop and what they can do next.

## Positioning

Model Builder brings senior-ML-engineer judgment to framing the problem and choosing the approach, and it owns the whole path to production, not just the training step. Every screen should reinforce that this is judgment plus a full pipeline, not a hyperparameter search that stops at an accuracy score.

## Brand Personality

Trustworthy, transparent, and guiding. The tool earns trust by showing its reasoning rather than asserting results, and it lowers the ML-expertise barrier by explaining unfamiliar steps without condescending to the engineers who use it. The register is a serious engineering tool that a skeptical practitioner would respect, closest in spirit to Linear: calm, disciplined, restrained in color, exact in hierarchy, the interface receding so the work is what stands out.

## Anti-references

Do not look or feel like a black-box AutoML dashboard (DataRobot, Vertex, enterprise-gray consoles that emit a score with no visible reasoning); this is the direct opposite of the glass-box intent. Do not look like a no-code business SaaS aimed at everyone (bright, rounded, illustration-heavy), which signals the wrong audience. Do not read as a generic AI-chat wrapper (a bare bubble stream with a sparkle icon and a gradient), which undersells the real infrastructure underneath. And do not become an overloaded enterprise admin surface (dense gray tables, tabs everywhere, every control crammed in with no hierarchy), which is the specific incoherence the current app is drifting toward as features accrete.

## Design Principles

Show the reasoning. Every methodology choice, evaluation, and recommendation is explained and open to inspection or override; the user can always sanity-check a call. This is the glass-box promise made concrete.

The loop is the product. Controls and layout should express the model lifecycle (train, recommend, deploy, monitor, retrain) as one connected path. When a state is ambiguous or two states disagree, resolve it in the interface rather than leaving the user to reconcile it.

Judgment on display. Surface the "why this approach" the way a senior engineer would triage a new problem, not as a score handed down. The reasoning is a first-class part of the output.

Earned familiarity over novelty. Standard affordances, one consistent component vocabulary, the tool disappearing into the task. Do not reinvent controls for flavor; a skeptical engineer should trust it on sight.

Progressive depth. Approachable enough that a non-ML engineer is never lost, dense enough that a practitioner can drill in. Density is available on demand, not forced on everyone.

## Accessibility & Inclusion

Target WCAG AA: body text at 4.5:1 or better against its background, visible focus states on every interactive element, keyboard-operable controls, and a reduced-motion alternative for any animation. Given the dark theme already in place, watch muted-gray text contrast on the near-black surfaces specifically.
