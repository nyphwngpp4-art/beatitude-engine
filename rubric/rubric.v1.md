# Beatitude Engine — Review Rubric v1

Version: 1.0
Date: 2026-08-24
Status: active

This rubric is the scoring contract for the Beatitude Engine. It is deliberately
identical to the eight public commitments on the Beatitude Standard page: the
engine gates on exactly what Agavi publishes. If this rubric and the public page
ever diverge, that is a bug.

## Scoring

Each artifact is scored against all eight commitments. Each commitment gets an
integer score:

- 2 = clear pass. No concern.
- 1 = concern. Not a violation, but a reviewer would want a human to look.
- 0 = violation. The artifact does the thing the commitment forbids.

## Verdict (derived, not judged separately)

- Misaligned      = any commitment scored 0
- Closely Aligned = no 0s, but one or more 1s
- Aligned         = all eight scored 2

## Council escalation

Escalate to the multi-model council when verdict == "Closely Aligned"
(the borderline band). Misaligned and Aligned do not escalate — Misaligned is
already a clear recommend-revise, Aligned is already a clear recommend-approve.
Council re-scores independently; its per-commitment scores replace the single
reviewer's for the human sign-off packet, and both opinions are shown.

## Ship-time policy (advise-only)

The engine NEVER blocks a pipeline and NEVER auto-issues the seal. Every verdict
routes to a human sign-off queue with a recommendation:

- Aligned        -> recommend approve
- Closely Aligned -> review recommended (council opinion attached)
- Misaligned     -> recommend revise (violated commitments + suggested fix attached)

A human signs off. Only a recorded human sign-off on a verdict authorizes the
"Beatitude Reviewed" seal for that artifact. No verdict, no seal. No sign-off,
no seal. This rule is the whole point — it is what keeps the seal honest.

## The eight commitments (scoring criteria)

### 1. honest_scoping  — "We tell you when you don't need us." (poor in spirit)
- 2: Recommends the smallest thing that solves the problem; declines to upsell.
- 1: Leans toward a larger engagement without clearly justifying the need.
- 0: Pushes a bigger/pricier scope the stated problem does not require.

### 2. human_impact_honesty — "We're honest about what automation costs your people." (those who mourn)
- 2: Names who is affected by the automation and how, plainly.
- 1: Touches staff impact but softens or buries it.
- 0: Automates people's work out of frame, or advises hiding the impact from staff.

### 3. no_hype — "No hype." (the meek)
- 2: Claims are measured and bounded; states limits.
- 1: Confident to the edge of overstatement; no outright false claim.
- 0: Inflated, guaranteed, or false capability claims ("flawless", "10x guaranteed").

### 4. build_integrity — "We build it right where no one is looking." (hunger for righteousness)
- 2: Holds unseen work to the same standard as visible work.
- 1: Minor corner-cutting that is unlikely to harm but is not best practice.
- 0: Knowingly ships a shortcut on the bet the client won't check.

### 5. dignified_rejection — "Bad-fit leads leave with dignity." (the merciful)
- 2: Turns away or declines gently; offers a useful redirect.
- 1: Efficient but curt; no redirect where one was easy.
- 0: Ghosts, demeans, or dismisses the person.

### 6. transparency — "You own everything." (pure in heart)
- 2: Plain pricing, clear ownership, no hidden terms or lock-in.
- 1: Terms are technically disclosed but hard to find or understand.
- 0: Hidden fees, buried penalties, lock-in traps, or concealed motive.

### 7. no_manipulation — "Nothing we build manipulates your customers." (the peacemakers)
- 2: Persuades by honest value only.
- 1: Uses mild pressure (real urgency stated strongly) that edges toward pushy.
- 0: Dark patterns: fake scarcity/countdowns, manufactured urgency, coercion.

### 8. standard_over_profit — "We'll walk from work that compromises this." (persecuted for righteousness)
- 2: The artifact itself upholds the standard even where a cheaper/greedier path existed.
- 1: Compromises slightly under commercial pressure.
- 0: The artifact IS the compromised work — it exists because profit beat principle.

## Changelog
- v1.0 (2026-08-24): initial rubric, mapped 1:1 to the public Beatitude Standard.
