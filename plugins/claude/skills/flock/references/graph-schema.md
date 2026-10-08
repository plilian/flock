# Flock graph schema

The helper stores records in SQLite at `.flock/flock.sqlite3`. Use JSON as the hand-off format between Codex reasoning and the deterministic graph helper.

```json
{
  "schema_version": 1,
  "ontology": {
    "entity_types": [
      {"name": "Organization", "description": "A named institution or company"}
    ],
    "relation_types": [
      {"name": "funds", "description": "Provides financial support to"}
    ]
  },
  "sources": [
    {"id": "src-report-2026", "name": "Annual report", "path": "sources/annual-report.pdf", "url": null}
  ],
  "entities": [
    {
      "id": "org-example",
      "label": "Example Organization",
      "type": "Organization",
      "description": "Short, neutral summary grounded in the cited source.",
      "evidence_status": "observed",
      "attributes": {"country": "Exampleland"},
      "source_refs": [
        {"source_id": "src-report-2026", "locator": "p. 12", "quote": "Short supporting excerpt."}
      ]
    },
    {
      "id": "org-funder",
      "label": "Example Foundation",
      "type": "Organization",
      "description": "A second source-grounded organization.",
      "attributes": {},
      "source_refs": [
        {"source_id": "src-report-2026", "locator": "p. 12", "quote": "Short supporting excerpt."}
      ]
    }
  ],
  "relationships": [
    {
      "id": "rel-funder-funds-example",
      "source": "org-funder",
      "target": "org-example",
      "type": "funds",
      "description": "Describe the relation without adding unsupported motive.",
      "evidence_status": "observed",
      "confidence": 0.86,
      "source_refs": [
        {"source_id": "src-report-2026", "locator": "p. 12", "quote": "Short supporting excerpt."}
      ]
    }
  ]
}
```

## Rules

- IDs are stable, unique strings. Reuse an entity ID when merging the same real-world concept from another selected source.
- Every entity and relationship `source_refs` entry points to a `sources[].id`. A reference can include a page, section, timestamp, URL fragment, or other locator plus a short exact quote.
- Set `evidence_status` on every entity and relationship: `observed` means directly stated in the cited source; `inferred` means the record is an interpretation from sources; `assumption` means a premise supplied for exploration and is not source evidence; `unclassified` is reserved for older records whose status has not been reviewed. Do not mark a claim observed because it merely sounds plausible.
- Keep quotes short and directly copied from the source. Do not store full documents in the graph database.
- `confidence` is optional and must be between `0` and `1`. It expresses extraction confidence, not probability that the claim is true.
- `attributes` must be a JSON object. Keep its values factual and source-linked.
- Ontology entries can be strings or objects with `name` and optional `description`.
- Importing a graph merges records by ID. It does not delete records omitted from the candidate file.

## Helper commands

Run these from the selected workspace, using the installed helper's absolute path:

```text
python <helper> --workspace . init --name "Research project"
python <helper> --workspace . graph validate --input .flock/staging/graph.json
python <helper> --workspace . graph import --input .flock/staging/graph.json
python <helper> --workspace . graph stats
python <helper> --workspace . graph audit
python <helper> --workspace . graph search --query "organization funding"
python <helper> --workspace . graph mermaid
python <helper> --workspace . graph export --output .flock/graph-export.json
```

`graph audit` saves a JSON audit under `.flock/audits/` by default. It checks citation coverage, missing locators or excerpts, unused sources, and unclassified records. It does not verify that quotes match their source, judge source quality, or detect semantic contradictions; ask the active host to read the audit file and check each cited source. Keep observed facts, model inferences, and assumptions visibly separate in the resulting Markdown review.
