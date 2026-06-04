# Methodology: Test-Driven Development (TDD) — sketch

> Not yet exercised. Included to prove the seam: the **same roster** runs a
> completely different choreography by swapping only this file. SDD has one big
> human gate up front; TDD has a mechanical gate on *every* micro-transition and no
> human halt. Same actors, different play.

## Shape
Micro-loop: red → green → refactor, repeated per unit of behavior.

## States
`pending → red → green → refactor → done`  (plus `blocked`)

## Gates
- **failing_test_exists** (mechanical): a new test exists AND fails for the stated
  reason. The hardest TDD gate — implementation cannot start until it holds.
- **test_passes** (mechanical): the previously-failing test now passes; full suite green.
- **refactor_clean** (judgment): no behavior change (suite still green); duplication removed.
- **constitution** (always-on, from profile).

## Phases

| State | Driver | Writes | Exit gate → next |
|---|---|---|---|
| pending | implementer | `tests/**` | **failing_test_exists** → red |
| red | implementer | `src/**` | **test_passes** → green |
| green | implementer | `src/**` | **refactor_clean** → refactor |
| refactor | reviewer | `progress/review_<f>.md` | **review_passed** → done |

Roster (implementer, reviewer) is unchanged from SDD. Only the state machine,
handoffs, and gate placement differ. That is the methodology dimension working.
