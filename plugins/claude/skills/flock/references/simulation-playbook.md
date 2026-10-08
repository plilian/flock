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

## Visualize a run

Refresh the local view after each completed round and after any later edits to the run:

    python <helper> --workspace . simulation visualize --id <run_id>

This writes .flock/runs/<run_id>/visualization.html by default. The self-contained snapshot has round playback, an agent inspector, an interaction graph based on recorded replies/reactions/follows, a searchable event feed, and JSON download. It embeds a point-in-time copy of the run, makes no network requests, and opens in a browser without a server. Share its path with the user and open it in the available local browser or file preview when supported.

## Report and interview

Use `python <helper> --workspace . simulation report-data --id <run_id>` for the completed timeline, profiles, event counts, and engagement totals. The active host writes the narrative report. Save it in `.flock/staging/report-<run_id>.md`, then persist it with:

```text
python <helper> --workspace . simulation save-report --id <run_id> --input .flock/staging/report-<run_id>.md
```

A report should include the scenario, settings, assumptions, main interaction patterns, disagreement, changes over rounds, and limitations. Distinguish computed activity counts from the host model's qualitative interpretation. Cite source IDs, page/section locators, or short excerpts for claims grounded in the source graph.

For an agent interview, retrieve the agent profile and its authored posts/comments/reactions from `report-data`. Answer in that synthetic persona's voice, clearly label the answer as a role-play, and do not claim it reflects an actual person.


