# Flock simulation playbook

The active host model is the simulator's language model. It receives the current scenario, synthetic agent profiles, and prior feed from `simulation prompt`, then writes the next round's actions. The helper enforces the selected social-platform action types and records the timeline in SQLite. Every run is synthetic and exploratory.

## Simulation spec

Save a candidate spec under `.flock/staging/` before creating a run:

```json
{
  "title": "Public response to the proposed transit plan",
  "scenario": "The city releases a proposal to ...",
  "platform": "reddit",
  "rounds": 5,
  "agents": [
    {
      "id": "resident-01",
      "name": "Maya Chen",
      "persona": "A renter who commutes by bus and follows local planning news.",
      "beliefs": ["Reliable service matters more than speed."],
      "goals": ["Understand the effect on her route."],
      "source_entities": ["entity-transit-riders"],
      "assumptions": ["Lives near the east branch; this is a simulation assumption."]
    },
    {
      "id": "small-business-01",
      "name": "Ravi Patel",
      "persona": "Owns a small shop near the proposed corridor.",
      "beliefs": ["Construction disruption could reduce visits."],
      "goals": ["Find practical ways to protect local businesses."],
      "source_entities": ["entity-corridor-merchants"],
      "assumptions": ["Has operated the shop for several years; this is a simulation assumption."]
    }
  ]
}
```

Use varied but plausible profiles. Do not assign real people's names or claim the simulated profiles represent sampled people. Mark every inferred demographic, motive, or personal detail as a simulation assumption.

## Run rounds

1. Validate the spec: `python <helper> --workspace . simulation validate --spec .flock/staging/run.json`.
2. Create it: `python <helper> --workspace . simulation create --spec .flock/staging/run.json`. Record the returned `run_id`.
3. Read the next round context: `python <helper> --workspace . simulation prompt --id <run_id>`.
4. Generate one action for each agent as a JSON array. Agents act simultaneously from the feed shown at the start of the round. Do not let them react to another action from that same round. Keep each agent's voice, goals, and knowledge distinct.
5. Save the JSON array under `.flock/staging/actions-<round>.json` and submit it: `python <helper> --workspace . simulation advance --id <run_id> --actions .flock/staging/actions-<round>.json`.
6. Refresh the visual snapshot after each completed round: `python <helper> --workspace . simulation visualize --id <run_id>`.
7. Repeat until the requested rounds finish or the user stops the run. The helper reports `status: complete` at the configured round count.

Example action batch for Reddit:

```json
[
  {"agent_id":"resident-01","type":"post","community":"city-planning","content":"Does the proposal explain how late-evening service changes?","stance":"questioning","emotion":"curious"},
  {"agent_id":"small-business-01","type":"join_community","community":"city-planning"}
]
```

Example action types:

| Platform | Actions | Required fields |
|---|---|---|
| Reddit-like | `post`, `comment`, `upvote`, `downvote`, `join_community` | `content` for posts/comments; `target_id` for comments/votes; `community` for community joins (optional on posts) |
| Twitter-like | `post`, `reply`, `like`, `repost`, `follow` | `content` for posts/replies; `target_id` for replies/reactions/follows |

Posts and comments can include optional `stance` and `emotion`. Keep content suitable for a synthetic scenario. Reactions target content IDs returned by earlier rounds; each agent gets one action per round.

For a source-grounded factual claim, an action may include graph `evidence_refs`. Use only IDs that appear in the agent's `grounding` records in `simulation prompt`:

```json
{"agent_id":"resident-01","type":"post","content":"The late service change affects the east branch.","stance":"concerned","evidence_refs":[{"record_type":"entity","record_id":"entity-transit-riders","source_id":"src-report-2026"}]}
```

The helper verifies that the source is cited by that graph record, rejects assumptions as source evidence, and saves the source name, locator, and short excerpt alongside the event. Do not add a reference to opinions, generated details, or claims without graph support. Replies already link to their target content in the recorded event graph.

## Compare variants with Scenario Lab

Build the agent roster once, then compare a baseline with focused alternatives. Each variant contains an independent scenario; the experiment begins with this shared configuration:

```json
{
  "title": "Transit proposal response",
  "research_question": "How does a correction change the discussion?",
  "platform": "reddit",
  "rounds": 4,
  "replicates": 3,
  "agents": [
    {"id":"resident-01","name":"Maya Chen","persona":"A bus rider who follows local planning news.","source_entities":["entity-transit-riders"],"beliefs":["Reliable service matters."],"goals":["Understand the effect on her route."],"assumptions":["Lives near the east branch."]},
    {"id":"shop-owner-01","name":"Ravi Patel","persona":"A shop owner near the proposed corridor.","source_entities":["entity-corridor-merchants"],"beliefs":["Construction may disrupt visits."],"goals":["Understand the construction plan."],"assumptions":["Runs a small shop."]}
  ],
  "variants": [
    {"id":"baseline","label":"Proposal only","baseline":true,"scenario":"The city releases its proposal. No correction is posted.","assumptions":[]},
    {"id":"correction","label":"Correction added","baseline":false,"scenario":"The same proposal is released. At the start of round 2, a source-linked correction is posted.","assumptions":["The correction reaches the discussion at the start of round 2."]}
  ]
}
```

Validate and create it with:

```text
python <helper> --workspace . scenario validate --spec .flock/staging/experiment.json
python <helper> --workspace . scenario create --spec .flock/staging/experiment.json
```

The returned experiment ID and run IDs identify each independent variant and replicate. Use the normal `simulation prompt`, `advance`, and `status` commands for every run. All runs start with identical profiles and settings; keep feeds and memories separate. Model usage scales with variants × replicates × rounds × agents.

Track progress and compare after the runs complete:

```text
python <helper> --workspace . scenario status --id <experiment_id>
python <helper> --workspace . scenario compare --id <experiment_id>
python <helper> --workspace . scenario visualize --id <experiment_id>
python <helper> --workspace . scenario save-report --id <experiment_id> --input .flock/staging/report.md
```

The comparison reports computed action metrics, median and min/max across replicates, and deltas against the baseline. A single replicate has no range. These ranges describe only the configured synthetic runs; they are not statistical confidence intervals or real-world probabilities. The visualization creates `.flock/experiments/<experiment_id>/comparison.html` and linked per-run HTML replays.

## Visualize a run

Refresh the local view after each completed round and after any later edits to the run:

    python <helper> --workspace . simulation visualize --id <run_id>

This writes .flock/runs/<run_id>/visualization.html by default. The self-contained snapshot has round playback, an agent inspector, an interaction graph based on recorded replies/reactions/follows, a searchable event feed, and JSON download. It embeds a point-in-time copy of the run, makes no network requests, and opens in a browser without a server. Share its path with the user and open it in the available local browser or file preview when supported.

## Report and interview

Use `python <helper> --workspace . simulation report-data --id <run_id>` for the completed timeline, profiles, event counts, and engagement totals. The active host writes the narrative report. Save it in `.flock/staging/report-<run_id>.md`, then persist it with:

```text
python <helper> --workspace . simulation save-report --id <run_id> --input .flock/staging/report-<run_id>.md
```

A report should include the scenario, settings, assumptions, main interaction patterns, disagreement, changes over rounds, and limitations. Distinguish computed activity counts from the host model's qualitative interpretation. Cite source IDs and page/section locators for graph-grounded claims; the saved event payload includes validated evidence references with the source excerpt and locator. Cite run, round, and event IDs for outcomes observed in the synthetic feed. Do not present unreferenced generated dialogue as verified source evidence.

For an agent interview, retrieve the agent profile and its authored posts/comments/reactions from `report-data`. Answer in that synthetic persona's voice, clearly label the answer as a role-play, and do not claim it reflects an actual person.


