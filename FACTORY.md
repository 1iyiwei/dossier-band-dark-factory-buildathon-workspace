# FACTORY

A five-seat software factory in Band Desktop. The seats plan, implement, check
each other independently, and route every failure to the seat that owns it.
The mandates in `mandates/` are generic: nothing in them names this track.

This repository is our **final run**: one fresh room per stage, one stage a
day (Nov 26–27, 2026), with the mandates in `mandates/` frozen from the
stage-1 dispatch to the end of stage 4. It follows a development run in
which we built and corrected the factory; see "How we got here" at the end.

## Design in one paragraph

Shipped tests are a small, known sample of what judges check; the rest is
written in the specification. So the factory's main check is **a second,
independent reading of the specification**: an Analyst seat turns every
testable sentence into a **requirement ledger** and writes **black-box
acceptance tests from the specification alone**, without reading the code,
plus fixtures that imitate how real sources mislead. The Implementer builds to
the specification, not to the tests. The Reviewer rebuilds from a clean clone,
runs every check itself, reads a sample of actual outputs for plausibility,
compares results per unit spent with the previous revision, and rejects with
evidence naming who owns the fix. A UX Reviewer drives the product as a user
(a browser when there's a UI; exploratory probing of the API when there
isn't). An increment closes only when the Reviewer accepts **and** every
ledger row has passing evidence or a recorded ruling.

## Seats

| Seat | Handle | Harness | Model | Effort | Owns |
|---|---|---|---|---|---|
| Coordinator | `@hack/coordinator` | Claude Code | `claude-sonnet-5-5` | medium | Plan, self-contained handoffs, tracking, final report; writes no code |
| Analyst | `@hack/analyst` | Claude Code | `claude-sonnet-5-5` | high | Requirement ledger, rulings on ambiguities, black-box acceptance tests, realistic fixtures |
| Implementer | `@hack/implementer` | Claude Code | `claude-sonnet-5-5` | high | Source, Dockerfile, RUN.md |
| Reviewer | `@hack/reviewer` | Claude Code | `claude-sonnet-5-5` | medium | Clean-clone build, all checks run independently, plausibility read, results per unit spent; accept or reject |
| UX Reviewer | `@hack/ux-reviewer` | Claude Code | `claude-haiku-5-5` | medium | Every named UI state at 375 px and desktop; outputs as a user reads them; exploratory API probing when there is no UI |

## Mechanisms (all in the mandates)

- **Independence.** The Analyst writes its tests before reading the
  implementation, and may read the code afterwards only to diagnose a disputed
  failure, never to bend a test to it. The Implementer never edits the
  Analyst's files.
- **The ledger is the contract.** `stage-N/requirements/LEDGER.md` lists every
  testable statement with its source sentence, how it is verified, and its
  status; `RULINGS.md` records every ambiguity, the reading adopted and why.
  Non-functional requirements (limits, budgets, timeouts, concurrency,
  restarts, upgrades, layout, accessibility) are ledger rows with a measurable
  check.
- **Realistic inputs.** The local test environment is cleaner than the real
  one, so the Analyst adds fixtures that imitate how real sources mislead
  (aggregators, partial figures that look like totals, values of the wrong
  kind, stale or contradictory pages, near-duplicates), written from how real
  sources look, never from shipped tests, with ledger rows for the outcome a
  careful person would want or an honest unknown.
- **Plausibility and results per unit spent.** Before accepting, the
  Reviewer reads actual outputs and rejects a value a domain-literate person
  would reject, and compares results per unit spent on a fixed workload with
  the previous revision; a worse ratio is a defect owned by the Implementer.
  The UX Reviewer reads outputs as their user would. The Implementer prefers
  authoritative sources, stops spending once a result is settled, and
  prefers an honest unknown to a confident wrong value.
- **Routing failures to their cause.** Every rejection names its owner: the
  Implementer for a code defect, the Analyst for a test that contradicts the
  specification, the Coordinator for a missing requirement or an environment
  problem.
- **Self-contained handoffs.** The Coordinator pastes the full task and the
  full specification text into every handoff; no seat is asked to read the
  room.
- **Increments in order.** A stage's specification is opened only when the
  previous folder is final; a finalized folder never changes; each new stage
  starts as a copy of the previous one.
- **Dark factory.** No seat asks the human anything after the dispatch;
  blockers go into the Coordinator's final report with evidence.
- **Reply with the result.** A seat posts by replying, once, to the message
  it is handling, so it does the work first and replies with the result; it
  never acknowledges first and reports later.
- **Traceable git.** Each seat commits under its own identity
  (`git -c user.name="<Seat>" -c user.email="<handle>@band.invalid"`), in
  small commits naming the work item and ledger IDs. No amend, rebase or
  squash.
- **Working economically.** Long command output goes to files; seats read only
  summaries and failures; no seat re-runs a check another seat already
  reported with evidence for the same revision; one heavy check at a time.
- **Memory between stages is the repository.** The ledger, rulings, tests
  and commit history carry what each stage learned into the next; we use no
  separate memory service.

## Standing it up

1. **Band Desktop → Agents → New agent**, once per seat in the table:
   - Name and handle as in the table; Runtime: Claude Code; Model and
     Reasoning effort as in the table (they must match the mandate's header).
   - Instructions: link the seat's `mandates/<seat>.md`.
   - Working directory: the absolute path of the result repository.
   - Claude customizations: your Claude setup (it carries the sign-in),
     but with no personal rule, e.g. "don't commit" in your CLAUDE.md, that
     covers the seats: Claude Code's permission check enforces it;
     MCP servers: only Band's; Permission mode: Auto.
   - Run **Test runtime** before **Create agent**, and again right before a
     dispatch (an expired sign-in stops a seat at its first turn).
2. If your Band owner name is not `hack`, replace `@hack/` in the mandates.
3. **Create a room with only the Coordinator** and check the participant list
   (Band can add a default agent; every seat in the room log needs a mandate).
4. **Dispatch** as the room's first message, choosing the Coordinator from the
   mention picker. The dispatch carries everything track-specific; our
   template:

   > @hack/coordinator You lead our factory. Build stage 1 of the track below,
   > coordinating the other seats. Track: … Result repository: … Stage folder:
   > …/stage-1/ (source, Dockerfile, RUN.md). Kickoff package (read-only): …
   > Stage 1 specification: read it in full from …/spec/stage-1.md and paste
   > the complete text into every handoff. Do not open any later stage's
   > specification. Local mock web: … explains how to run it beside the
   > service; use it to run the service, not as a source of answers. Checks:
   > `python -m harness run --track … --repo … --stage N --out <new dir>`; add
   > `--mode isolated` for the final check. Only part of each stage's checks
   > ship; the rest are in the specification. Run one check at a time across
   > the band. Resolve everything within the band. Do not ask me anything;
   > record any blocker with its evidence in your final report.

   Each stage's dispatch differs from the others only in the stage number,
   paths and check-folder names; it is the first message in each
   `room-N.json`.

## How it caught bad work (final run)

Times are Pacific (PST), from commits and the room logs.

### Stage 1 (Nov 26, 09:31–10:08)

| Who | What | Fix |
|---|---|---|
| UX Reviewer | **REJECT `771906f`**: import refused a `www.`-prefixed domain (§10), chunked request bodies were dropped, a 405 status the spec doesn't name | `1886f3b` |
| Reviewer | Residual failures on `1886f3b`: five bugs in the Analyst's tests, and empty or null bodies not answered as malformed requests | Analyst fixed its tests (`4b3d7ac`); Implementer `c0c6623` |
| Analyst | Wrote realistic fixtures (an aggregator contradicting the company's own site, a region where a city belongs) and ruled from the specification that stage 1 accepts any supported value (RULINGS 6, 7: Appendix A decides support "by these rules alone") | Recorded rulings |

Stage 1 final: `c0c6623`, ledger 167 rows (0 failing, 0 untested), Analyst
suite 321 passing, Reviewer isolated pass. Results per unit, from the
Coordinator's report: 6 of 6 fields for 5–8 units on four companies; 0–4 of
6 for 35–38 units on companies that need research.

### Stage 2 (Nov 26 13:53 – Nov 27 08:33)

| Who | What | Fix |
|---|---|---|
| UX Reviewer | Polish on `a41b62a`: raw field names on evidence, the refresh button wrapping at 375 px, no headcount hint | `5a06057` |
| Reviewer | **REJECT `5a06057`**: the stage-1 import could not derive candidates from uncited pages; stale test expectations and a fixture-isolation bug | Implementer `6b5b566` (candidates from every cited excerpt); Analyst `5f1c95e` |
| Analyst → Reviewer | **REJECT `6b5b566`** on the Analyst's slow-provider test (BD-5): with every provider call delayed 3 s, the build ended `ready` with all fields unknown, because the more sequential stage-2 reads ran out the gathering window | `a70e5c6`: one parallel round of reads when time runs short |
| UX Reviewer | Misleading wording on a failed dossier with no successful build | `158fc8c` |

Stage 2 final: `158fc8c`, ledger 286 rows (272 passing, 14 ruled, 0 open),
Analyst suite 411 passing, Reviewer isolated pass on a fresh clone. Results
per unit fell from 18.0 to 7.2 known fields per 100 units; the Reviewer
accepted it because rendering a page costs 3 units. Most of the wall clock
was two stalls (see "Human input").

### Stage 3 (Nov 27, 13:01–15:21)

| Who | What | Fix |
|---|---|---|
| Reviewer | A partial accept of `2371536` only: the Analyst's tests were not committed yet | Analyst committed; full run, then full accept |
| Analyst | The full run found four bugs in its own tests and one clock-stall flake | Fixed in `00f3d59`; RULINGS 76 |
| Reviewer | Plausibility sample against the local web: history, change feed, `as_of`, `/values`, a kill-and-restart, the 422 and 404 cases | Accepted |

Stage 3 final: service `2371536`, ledger 400 rows (399 passing, 1 ruled),
Analyst suite 518 passing, Reviewer isolated pass on a fresh clone (stages
1–3). No service defect found. Spend on the same workload: 75 units against
74 at stage 2, with executives added.

### Stage 4 (Nov 27, 17:48–20:23)

| Who | What | Fix |
|---|---|---|
| Reviewer | **REJECT `e231e29`**: `GET /values` listed investors before executives | `005076e`, with a test; the Implementer audited every response's field order |
| Analyst | Stale carried tests (the eight-field world, the `as_of` key set) | `37ddcab`, `f6421bc` |
| UX Reviewer | 68 of 200 units charged when a provider's port was dead | Ruled not a bug (stage-1 §9: unanswered calls cost units) |
| Reviewer | Plausibility read (lineage, a lookalike domain, investors, origins) and results per unit on a fixed four-company workload: one more unit per build for one more known field, so known fields per unit rose (0.076 → 0.090, 0.083 → 0.096) | Final accept at `6b0a084` |

Stage 4 final: service `005076e`, ledger 470 rows (469 passing, 1 ruled),
Analyst suite 606 passing (upgrades from stage-1, -2 and -3 exports and
SIGKILL restarts included), Reviewer isolated pass on a fresh clone (stages
1–4). Left open, in the Coordinator's report: no Tavily fallback when the
Nimble search fails; a build interrupted by a restart ends `failed` (the
specification allows it); the UI shows no executives, investors or origins
(the specification allows it).

Our own checks after each stage: the shipped harness in normal and isolated
mode claims that stage; `--all --mode isolated` after stage 4 claims stages
1–4; no earlier stage folder changed; every commit under `stage-N/` is by a
seat identity.

## Measured cost and time

Cost is Band's list-price estimate (`band usage`), not a bill.

| Seat | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|---|---|---|---|---|
| Analyst | $3.51 | $9.87 | $5.66 | $6.53 |
| Implementer | $3.74 | $6.07 | $5.29 | $4.22 |
| Reviewer | $0.62 | $1.75 | $0.81 | $1.54 |
| Coordinator | $0.59 | $2.05 | $0.66 | $1.03 |
| UX Reviewer | $0.09 | $0.16 | $0.12 | $0.30 |
| **Room total** | **$8.55** (29.8M tokens) | **$19.89** (66.3M) | **$12.54** (64.3M) | **$13.63** (80.7M) |
| **Time** | 37 min | 18.7 h wall clock, under 3 h of work | 2 h 20 min | 2 h 35 min |

All four stages: **$54.61**, against $108.03 for the development run at the
same estimates. Each stage ran in its own room (`room-1.json` …
`room-4.json`).

## Human input, disclosed

After each dispatch, the only human actions were:

- **Before each stage:** a restart and **Test runtime** of all five seats.
- **Stage 2, two nudges in the room**, each telling a seat only what its own
  session log already said:
  - Nov 26 18:29: "@hack/implementer Your report for a70e5c6 was not
    delivered. Please post it now." The Implementer had committed the fix at
    15:16, then settled the request with no reply by mistake; every seat was
    waiting for its report.
  - Nov 27 08:31: "@hack/analyst Your report on 158fc8c was not delivered.
    Please post it now." The Analyst had finished its run (411 passing) and
    committed the ledger by 19:53, but had no request to reply to: the
    Coordinator's request (sent 18:53 with `band send` from a shell command)
    reached the Analyst only when its session restarted before stage 3, at
    11:58. The Analyst then answered it in room 2 ("This request is already
    done"), which is why `room-2.json` has a message after the final report.
- **Stages 1, 3 and 4:** none.

## Live result

`dossier-runway.com.json` is `GET /dossiers/runway.com` from `stage-4/`,
built against the live web on Nov 28 05:39 UTC, unedited. State `ready`, 79
of 80 budget units spent. Of eight fields, two are `known`, three
`contested` and three `unknown`:

- **Known:** executives (the CTO, right) and HQ city "North America" (a
  region, not a city).
- **Contested:** founded year (2018, right, against a 2023 candidate),
  headcount range (1001–5000 against three smaller ranges) and total funding
  (US$2 million, against $8.5M, $35M and $50M; none is the total).
- **Unknown:** legal name, CEO, and investors (four candidates, all real
  investors, but no value).

The development run's stage 4 gave about the same picture (two known, two
contested, four unknown): this run gained the executive and lost the
founded year's certainty. The region-for-a-city case is the clearest: the
Analyst wrote a fixture for it in stage 1, but ruled, from the
specification's own rule that support is decided "by these rules alone",
that "North America" is a supported value (RULINGS 7), and that ruling stood
through stage 4.

## What the factory still misses, and how we'd change it

- **A seat that finishes without a request to answer.** Both stage-2 stalls
  had this shape: the work was done and committed, and the report never
  reached the room, so every seat waited and nothing woke them. One seat
  closed its request with no reply; the other's request arrived only after a
  restart. Changes: every seat, before going idle, compares `git log` with
  what it has reported and reports anything unreported to the Coordinator;
  the Coordinator, before waiting, checks for commits nobody has reported.
  A restart of a seat that says its report is undelivered is the cheapest
  human fix, before a nudge.
- **A watch that can't see its run.** The Analyst's progress monitor looked
  for `PASSED` and `FAILED` lines in a test run that printed dots, so it
  never fired. A seat should check that its watch matches the output format
  before relying on it.
- **Plausibility against the specification.** The v3 rules made the band
  measure and report results per unit and read outputs, and the ratio
  improved where the specification allowed it. Where the specification
  itself accepts an implausible value (a region as a city), the band
  followed the specification. A plausibility finding the specification
  doesn't support should still be reported, as a known weakness of the
  answer, rather than only ruled.
- **One real case before closing.** The live build still ran only after
  acceptance. A live run judged by the Reviewer before the stage closes
  would let the band see real sources; it needs a key in the seat's
  environment, never in a mandate or the repository.

## How we got here: the development run

The factory was built and corrected in a development run (Nov 13–26,
[its repository](https://github.com/1iyiwei/dossier-band-dark-factory-buildathon-workspace-dev)),
which reached stage 4 at $108.03. What it taught us, and what changed:

- **Three Opus seats (draft v1)** were 85% of the spend and hit the 5-hour
  usage limit in about 45 minutes; v2 moved every seat to Sonnet or Haiku,
  lowered effort for coordination and review, and added the
  working-economically rules.
- **A fresh room per stage**: a seat keeps one session per room, so a
  resumed room re-reads everything; a new room is much cheaper.
- **Where the Analyst's files live**: the first Coordinator handoff put the
  ledger at the repository root, against the Analyst's mandate; we added the
  rule that it lives under `requirements/` in each stage folder.
- **A personal setting blocked the band**: the seats inherited the owner's
  "don't commit" rule, and every seat commit was denied. A factory seat must
  not inherit its owner's personal instructions.
- **Reply with the result**: seats that acknowledged first had nowhere to
  post their results hours later; we added "Replying in the room" to all
  five mandates, and every result reached the room in the development
  stage 4.
- **Rules, not answers**: the development run's live result had right
  mechanics and wrong values (a region as a city, a funding round as a
  total). That gave the v3 rules this run used: realistic inputs for the
  Analyst, a plausibility read and results per unit for the Reviewer,
  outputs as a user reads them for the UX Reviewer, and results per unit
  spent for the Implementer.
- **Human input in the development run**: messages and restarts around
  usage limits and API errors in every stage, all disclosed in its
  FACTORY.md. The final run needed two nudges, both in stage 2.
- **From the toy practice run:** a default agent Band adds to new rooms stays
  in the room log and needs a mandate (we now check the participant list);
  commits defaulted to the human's git identity until each seat committed
  under its own; typed mentions don't route, the mention picker does.
