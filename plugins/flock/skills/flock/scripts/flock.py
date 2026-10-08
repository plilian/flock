#!/usr/bin/env python3
"""Workspace-local graph and simulation store for the Flock Codex plugin.

This helper is deliberately model-free: Codex performs reasoning in the active
session; this file validates and persists the resulting graph and simulation.
It uses only Python's standard library and makes no network requests.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PLATFORMS = {"reddit", "twitter"}
ACTION_TYPES = {
    "reddit": {"post", "comment", "upvote", "downvote", "join_community"},
    "twitter": {"post", "reply", "like", "repost", "follow"},
}


class FlockError(Exception):
    """A user-correctable Flock command error."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def fail(message: str) -> None:
    raise FlockError(message)


def workspace_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        fail(f"Workspace directory does not exist: {path}")
    return path


def data_dir(workspace: Path) -> Path:
    return workspace / ".flock"


def database_path(workspace: Path) -> Path:
    return data_dir(workspace) / "flock.sqlite3"


def connect(workspace: Path) -> sqlite3.Connection:
    db = database_path(workspace)
    if not db.is_file():
        fail(f"Flock is not initialized in {workspace}. Run `init` first.")
    connection = sqlite3.connect(db, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(workspace: Path, name: str) -> dict[str, Any]:
    root = data_dir(workspace)
    if root.exists() and any(root.iterdir()):
        fail(f"{root} already contains data; refusing to overwrite it.")
    root.mkdir(parents=True, exist_ok=True)
    (root / "staging").mkdir(exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    ignore_file = root / ".gitignore"
    if not ignore_file.exists():
        ignore_file.write_text("*\n!.gitignore\n", encoding="utf-8")
    with sqlite3.connect(database_path(workspace)) as db:
        db.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS project (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                schema_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT,
                url TEXT,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                attributes_json TEXT NOT NULL DEFAULT '{}',
                source_refs_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS entities_label_idx ON entities(label);
            CREATE INDEX IF NOT EXISTS entities_type_idx ON entities(entity_type);
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES entities(id),
                target_id TEXT NOT NULL REFERENCES entities(id),
                relation_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                confidence REAL,
                source_refs_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS relationships_source_idx ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS relationships_target_idx ON relationships(target_id);
            CREATE TABLE IF NOT EXISTS ontology (
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (kind, name)
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                scenario TEXT NOT NULL,
                platform TEXT NOT NULL,
                total_rounds INTEGER NOT NULL,
                current_round INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agents (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                followed_json TEXT NOT NULL DEFAULT '[]',
                communities_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (run_id, id)
            );
            CREATE TABLE IF NOT EXISTS posts (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                id TEXT NOT NULL,
                round INTEGER NOT NULL,
                author_id TEXT NOT NULL,
                community TEXT,
                content TEXT NOT NULL,
                stance TEXT NOT NULL DEFAULT 'unclear',
                emotion TEXT NOT NULL DEFAULT 'neutral',
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, id)
            );
            CREATE INDEX IF NOT EXISTS posts_round_idx ON posts(run_id, round);
            CREATE TABLE IF NOT EXISTS comments (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                id TEXT NOT NULL,
                round INTEGER NOT NULL,
                author_id TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                stance TEXT NOT NULL DEFAULT 'unclear',
                emotion TEXT NOT NULL DEFAULT 'neutral',
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, id)
            );
            CREATE INDEX IF NOT EXISTS comments_parent_idx ON comments(run_id, parent_id);
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                id TEXT NOT NULL,
                round INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_id TEXT,
                content TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, id)
            );
            CREATE INDEX IF NOT EXISTS events_round_idx ON events(run_id, round);
            CREATE TABLE IF NOT EXISTS reports (
                run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                markdown TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        project_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO project(id, name, created_at, schema_version) VALUES (?, ?, ?, ?)",
            (project_id, name.strip() or "Flock project", now(), SCHEMA_VERSION),
        )
    return {
        "project_id": project_id,
        "name": name.strip() or "Flock project",
        "workspace": str(workspace),
        "database": str(database_path(workspace)),
        "schema_version": SCHEMA_VERSION,
    }


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"File not found: {path}")
    except json.JSONDecodeError as error:
        fail(f"Invalid JSON in {path}: {error}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def require_text(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{context}: `{key}` must be a non-empty string.")
    return value.strip()


def validate_graph(graph: Any) -> dict[str, Any]:
    if not isinstance(graph, dict):
        fail("Graph file must contain a JSON object.")
    if graph.get("schema_version") != SCHEMA_VERSION:
        fail(f"Graph `schema_version` must be {SCHEMA_VERSION}.")
    ontology = graph.get("ontology", {})
    if not isinstance(ontology, dict):
        fail("Graph `ontology` must be an object.")
    for kind in ("entity_types", "relation_types"):
        values = ontology.get(kind, [])
        if not isinstance(values, list):
            fail(f"Graph `ontology.{kind}` must be an array.")
        for index, value in enumerate(values):
            if isinstance(value, str):
                continue
            if not isinstance(value, dict) or not isinstance(value.get("name"), str):
                fail(f"Graph `ontology.{kind}[{index}]` must be a name string or object with `name`.")
    sources = graph.get("sources", [])
    entities = graph.get("entities", [])
    relationships = graph.get("relationships", [])
    if not all(isinstance(items, list) for items in (sources, entities, relationships)):
        fail("Graph `sources`, `entities`, and `relationships` must be arrays.")
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            fail(f"Source at index {index} must be an object.")
        sid = require_text(source, "id", f"Source {index}")
        require_text(source, "name", f"Source {sid}")
        if sid in source_ids:
            fail(f"Duplicate source id: {sid}")
        source_ids.add(sid)
    entity_ids: set[str] = set()
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            fail(f"Entity at index {index} must be an object.")
        eid = require_text(entity, "id", f"Entity {index}")
        require_text(entity, "label", f"Entity {eid}")
        require_text(entity, "type", f"Entity {eid}")
        if eid in entity_ids:
            fail(f"Duplicate entity id: {eid}")
        entity_ids.add(eid)
        if not isinstance(entity.get("attributes", {}), dict):
            fail(f"Entity {eid} `attributes` must be an object.")
        _validate_source_refs(entity.get("source_refs", []), source_ids, f"Entity {eid}")
    relationship_ids: set[str] = set()
    for index, relation in enumerate(relationships):
        if not isinstance(relation, dict):
            fail(f"Relationship at index {index} must be an object.")
        rid = require_text(relation, "id", f"Relationship {index}")
        source_id = require_text(relation, "source", f"Relationship {rid}")
        target_id = require_text(relation, "target", f"Relationship {rid}")
        require_text(relation, "type", f"Relationship {rid}")
        if rid in relationship_ids:
            fail(f"Duplicate relationship id: {rid}")
        if source_id not in entity_ids or target_id not in entity_ids:
            fail(f"Relationship {rid} references an unknown entity.")
        relationship_ids.add(rid)
        confidence = relation.get("confidence")
        if confidence is not None and (not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1):
            fail(f"Relationship {rid} confidence must be between 0 and 1.")
        _validate_source_refs(relation.get("source_refs", []), source_ids, f"Relationship {rid}")
    return graph


def _validate_source_refs(refs: Any, source_ids: set[str], context: str) -> None:
    if not isinstance(refs, list):
        fail(f"{context} `source_refs` must be an array.")
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            fail(f"{context} source reference {index} must be an object.")
        source_id = require_text(ref, "source_id", f"{context} source reference {index}")
        if source_id not in source_ids:
            fail(f"{context} references unknown source `{source_id}`.")
        locator = ref.get("locator", "")
        quote = ref.get("quote", "")
        if not isinstance(locator, str) or not isinstance(quote, str):
            fail(f"{context} source reference locator and quote must be strings.")


def import_graph(workspace: Path, graph_file: Path) -> dict[str, Any]:
    graph = validate_graph(read_json(graph_file))
    with connect(workspace) as db:
        for source in graph.get("sources", []):
            db.execute(
                "INSERT INTO sources(id,name,path,url,added_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name,path=excluded.path,url=excluded.url",
                (source["id"], source["name"], source.get("path"), source.get("url"), now()),
            )
        for item in graph.get("ontology", {}).get("entity_types", []):
            name = item if isinstance(item, str) else item["name"]
            description = "" if isinstance(item, str) else item.get("description", "")
            db.execute("INSERT OR REPLACE INTO ontology(kind,name,description) VALUES('entity',?,?)", (name, description))
        for item in graph.get("ontology", {}).get("relation_types", []):
            name = item if isinstance(item, str) else item["name"]
            description = "" if isinstance(item, str) else item.get("description", "")
            db.execute("INSERT OR REPLACE INTO ontology(kind,name,description) VALUES('relation',?,?)", (name, description))
        for entity in graph.get("entities", []):
            db.execute(
                "INSERT INTO entities(id,label,entity_type,description,attributes_json,source_refs_json) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label, "
                "entity_type=excluded.entity_type, description=excluded.description, "
                "attributes_json=excluded.attributes_json, source_refs_json=excluded.source_refs_json",
                (
                    entity["id"], entity["label"], entity["type"], entity.get("description", ""),
                    json.dumps(entity.get("attributes", {}), ensure_ascii=False),
                    json.dumps(entity.get("source_refs", []), ensure_ascii=False),
                ),
            )
        for relation in graph.get("relationships", []):
            db.execute(
                "INSERT INTO relationships(id,source_id,target_id,relation_type,description,confidence,source_refs_json) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_id=excluded.source_id, "
                "target_id=excluded.target_id, relation_type=excluded.relation_type, "
                "description=excluded.description, confidence=excluded.confidence, source_refs_json=excluded.source_refs_json",
                (
                    relation["id"], relation["source"], relation["target"], relation["type"],
                    relation.get("description", ""), relation.get("confidence"),
                    json.dumps(relation.get("source_refs", []), ensure_ascii=False),
                ),
            )
    return {"imported_sources": len(graph.get("sources", [])), "imported_entities": len(graph.get("entities", [])), "imported_relationships": len(graph.get("relationships", []))}


def graph_as_json(db: sqlite3.Connection) -> dict[str, Any]:
    project = db.execute("SELECT * FROM project LIMIT 1").fetchone()
    ontology: dict[str, list[dict[str, str]]] = {"entity_types": [], "relation_types": []}
    for row in db.execute("SELECT kind,name,description FROM ontology ORDER BY kind,name"):
        key = "entity_types" if row["kind"] == "entity" else "relation_types"
        ontology[key].append({"name": row["name"], "description": row["description"]})
    sources = [dict(row) for row in db.execute("SELECT id,name,path,url FROM sources ORDER BY name")]
    entities = []
    for row in db.execute("SELECT * FROM entities ORDER BY label"):
        entities.append({
            "id": row["id"], "label": row["label"], "type": row["entity_type"],
            "description": row["description"], "attributes": json.loads(row["attributes_json"]),
            "source_refs": json.loads(row["source_refs_json"]),
        })
    relationships = []
    for row in db.execute("SELECT * FROM relationships ORDER BY source_id,target_id,relation_type"):
        relationships.append({
            "id": row["id"], "source": row["source_id"], "target": row["target_id"],
            "type": row["relation_type"], "description": row["description"],
            "confidence": row["confidence"], "source_refs": json.loads(row["source_refs_json"]),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {"id": project["id"], "name": project["name"], "created_at": project["created_at"]},
        "ontology": ontology, "sources": sources, "entities": entities, "relationships": relationships,
    }


def graph_stats(workspace: Path) -> dict[str, Any]:
    with connect(workspace) as db:
        counts = {
            "sources": db.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "entities": db.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "relationships": db.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
        }
        counts["entities_by_type"] = {row["entity_type"]: row["count"] for row in db.execute("SELECT entity_type,COUNT(*) count FROM entities GROUP BY entity_type ORDER BY entity_type")}
        counts["relationships_by_type"] = {row["relation_type"]: row["count"] for row in db.execute("SELECT relation_type,COUNT(*) count FROM relationships GROUP BY relation_type ORDER BY relation_type")}
        return counts


def graph_search(workspace: Path, query: str, limit: int) -> dict[str, Any]:
    terms = [term.casefold() for term in re.findall(r"[\w-]+", query) if term]
    if not terms:
        fail("Search query must contain at least one word.")
    with connect(workspace) as db:
        entities = []
        for row in db.execute("SELECT * FROM entities ORDER BY label"):
            haystack = " ".join((row["label"], row["entity_type"], row["description"], row["attributes_json"])).casefold()
            if all(term in haystack for term in terms):
                entities.append({"id": row["id"], "label": row["label"], "type": row["entity_type"], "description": row["description"], "source_refs": json.loads(row["source_refs_json"])})
                if len(entities) >= limit:
                    break
        ids = [item["id"] for item in entities]
        relations = []
        if ids:
            marks = ",".join("?" for _ in ids)
            rows = db.execute(f"SELECT * FROM relationships WHERE source_id IN ({marks}) OR target_id IN ({marks}) ORDER BY relation_type LIMIT ?", [*ids, *ids, limit * 3])
            relations = [dict(row) for row in rows]
            for item in relations:
                item["source_refs"] = json.loads(item.pop("source_refs_json"))
        return {"query": query, "entities": entities, "relationships": relations}


def graph_mermaid(workspace: Path, limit: int) -> str:
    with connect(workspace) as db:
        entities = list(db.execute("SELECT id,label,entity_type FROM entities ORDER BY label LIMIT ?", (limit,)))
        id_map = {row["id"]: f"n{i}" for i, row in enumerate(entities, 1)}
        lines = ["graph LR"]
        for row in entities:
            label = row["label"].replace('"', "'").replace("[", "(").replace("]", ")")
            lines.append(f'  {id_map[row["id"]]}["{label}<br/>{row["entity_type"]}"]')
        if id_map:
            marks = ",".join("?" for _ in id_map)
            rows = db.execute(f"SELECT source_id,target_id,relation_type FROM relationships WHERE source_id IN ({marks}) AND target_id IN ({marks}) ORDER BY relation_type", [*id_map, *id_map])
            for row in rows:
                if row["source_id"] in id_map and row["target_id"] in id_map:
                    label = row["relation_type"].replace('"', "'")
                    lines.append(f'  {id_map[row["source_id"]]} -->|"{label}"| {id_map[row["target_id"]]}')
        return "\n".join(lines) + "\n"


def validate_spec(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        fail("Simulation spec must be a JSON object.")
    require_text(spec, "title", "Simulation spec")
    require_text(spec, "scenario", "Simulation spec")
    platform = require_text(spec, "platform", "Simulation spec").lower()
    if platform not in PLATFORMS:
        fail("Simulation platform must be `reddit` or `twitter`.")
    rounds = spec.get("rounds")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 50:
        fail("Simulation `rounds` must be an integer from 1 to 50.")
    agents = spec.get("agents")
    if not isinstance(agents, list) or not 2 <= len(agents) <= 100:
        fail("Simulation must include between 2 and 100 agents.")
    ids: set[str] = set()
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            fail(f"Agent at index {index} must be an object.")
        aid = require_text(agent, "id", f"Agent {index}")
        require_text(agent, "name", f"Agent {aid}")
        require_text(agent, "persona", f"Agent {aid}")
        if aid in ids:
            fail(f"Duplicate agent id: {aid}")
        ids.add(aid)
        if not isinstance(agent.get("beliefs", []), list) or not isinstance(agent.get("goals", []), list):
            fail(f"Agent {aid} `beliefs` and `goals` must be arrays.")
    return {"title": spec["title"].strip(), "scenario": spec["scenario"].strip(), "platform": platform, "rounds": rounds, "agents": agents}


def create_run(workspace: Path, spec_file: Path) -> dict[str, Any]:
    spec = validate_spec(read_json(spec_file))
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    timestamp = now()
    with connect(workspace) as db:
        db.execute(
            "INSERT INTO runs(id,title,scenario,platform,total_rounds,current_round,status,created_at,updated_at) VALUES(?,?,?,?,?,0,'ready',?,?)",
            (run_id, spec["title"], spec["scenario"], spec["platform"], spec["rounds"], timestamp, timestamp),
        )
        for agent in spec["agents"]:
            profile = {key: value for key, value in agent.items() if key not in {"id", "name"}}
            db.execute("INSERT INTO agents(run_id,id,name,profile_json) VALUES(?,?,?,?)", (run_id, agent["id"], agent["name"], json.dumps(profile, ensure_ascii=False)))
    return {"run_id": run_id, "title": spec["title"], "platform": spec["platform"], "agents": len(spec["agents"]), "rounds": spec["rounds"], "status": "ready"}


def run_row(db: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        fail(f"Unknown simulation run: {run_id}")
    return row


def run_status(workspace: Path, run_id: str) -> dict[str, Any]:
    with connect(workspace) as db:
        run = run_row(db, run_id)
        return {key: run[key] for key in run.keys()}


def simulation_prompt(workspace: Path, run_id: str) -> dict[str, Any]:
    with connect(workspace) as db:
        run = run_row(db, run_id)
        if run["status"] == "complete":
            fail("This simulation is already complete.")
        round_number = run["current_round"] + 1
        agents = []
        for row in db.execute("SELECT id,name,profile_json,followed_json,communities_json FROM agents WHERE run_id=? ORDER BY id", (run_id,)):
            agents.append({"id": row["id"], "name": row["name"], **json.loads(row["profile_json"]), "following": json.loads(row["followed_json"]), "communities": json.loads(row["communities_json"])})
        posts = []
        for row in db.execute("SELECT * FROM posts WHERE run_id=? ORDER BY round DESC,created_at DESC LIMIT 40", (run_id,)):
            posts.append(dict(row))
        comments = []
        for row in db.execute("SELECT * FROM comments WHERE run_id=? ORDER BY round DESC,created_at DESC LIMIT 40", (run_id,)):
            comments.append(dict(row))
        return {
            "run_id": run_id, "title": run["title"], "scenario": run["scenario"],
            "platform": run["platform"], "round": round_number, "total_rounds": run["total_rounds"],
            "agents": agents, "recent_posts": posts, "recent_comments": comments,
            "action_types": sorted(ACTION_TYPES[run["platform"]]),
            "instructions": "Generate one valid action per agent for this round as a JSON array. Use only information in the scenario, each profile, and the feed shown here. Actions occur simultaneously; do not react to content created in this same round.",
        }


def advance_run(workspace: Path, run_id: str, actions_file: Path) -> dict[str, Any]:
    actions = read_json(actions_file)
    if not isinstance(actions, list):
        fail("Actions file must contain a JSON array.")
    timestamp = now()
    with connect(workspace) as db:
        run = run_row(db, run_id)
        if run["status"] == "complete":
            fail("This simulation is already complete.")
        round_number = run["current_round"] + 1
        agents = {row["id"]: row for row in db.execute("SELECT * FROM agents WHERE run_id=?", (run_id,))}
        already = {row["agent_id"] for row in db.execute("SELECT agent_id FROM events WHERE run_id=? AND round=?", (run_id, round_number))}
        known_posts = {row["id"] for row in db.execute("SELECT id FROM posts WHERE run_id=?", (run_id,))}
        known_comments = {row["id"] for row in db.execute("SELECT id FROM comments WHERE run_id=?", (run_id,))}
        seen: set[str] = set()
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                fail(f"Action {index} must be an object.")
            agent_id = require_text(action, "agent_id", f"Action {index}")
            action_type = require_text(action, "type", f"Action {index}").lower()
            if agent_id not in agents:
                fail(f"Action references unknown agent: {agent_id}")
            if action_type not in ACTION_TYPES[run["platform"]]:
                fail(f"Action `{action_type}` is invalid on {run['platform']}.")
            if agent_id in seen or agent_id in already:
                fail(f"Agent {agent_id} already has an action in round {round_number}.")
            seen.add(agent_id)
            target_id = action.get("target_id")
            if action_type in {"post", "join_community"}:
                target_id = None
            elif action_type in {"comment", "reply"}:
                target_id = require_text(action, "target_id", f"Action {index}")
                if target_id not in known_posts and target_id not in known_comments:
                    fail(f"Action {index} targets unknown content `{target_id}`.")
            elif action_type in {"upvote", "downvote", "like", "repost"}:
                target_id = require_text(action, "target_id", f"Action {index}")
                if target_id not in known_posts and target_id not in known_comments:
                    fail(f"Action {index} targets unknown content `{target_id}`.")
            elif action_type == "follow":
                target_id = require_text(action, "target_id", f"Action {index}")
                if target_id not in agents or target_id == agent_id:
                    fail(f"Action {index} must follow another known agent.")
            content = action.get("content", "")
            community = action.get("community", "")
            stance = action.get("stance", "unclear")
            emotion = action.get("emotion", "neutral")
            if not isinstance(content, str) or not isinstance(community, str):
                fail(f"Action {index} `content` and `community` must be strings.")
            if action_type in {"post", "comment", "reply"} and not content.strip():
                fail(f"Action {index} requires non-empty `content`.")
            if len(content) > 4000:
                fail(f"Action {index} content exceeds 4,000 characters.")
            if not isinstance(stance, str) or not isinstance(emotion, str):
                fail(f"Action {index} stance and emotion must be strings.")
            event_id = uuid.uuid4().hex
            payload = {key: value for key, value in action.items() if key not in {"agent_id", "type", "target_id", "content", "community", "stance", "emotion"}}
            if action_type == "post":
                post_id = f"p_{event_id[:12]}"
                db.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?)", (run_id, post_id, round_number, agent_id, community or None, content.strip(), stance, emotion, timestamp))
                target_id = post_id
            elif action_type in {"comment", "reply"}:
                comment_id = f"c_{event_id[:12]}"
                db.execute("INSERT INTO comments VALUES(?,?,?,?,?,?,?,?,?)", (run_id, comment_id, round_number, agent_id, target_id, content.strip(), stance, emotion, timestamp))
                target_id = comment_id
            elif action_type == "join_community":
                community_name = require_text(action, "community", f"Action {index}")
                communities = json.loads(agents[agent_id]["communities_json"])
                if community_name not in communities:
                    communities.append(community_name)
                    db.execute("UPDATE agents SET communities_json=? WHERE run_id=? AND id=?", (json.dumps(communities, ensure_ascii=False), run_id, agent_id))
                payload["community"] = community_name
            elif action_type == "follow":
                following = json.loads(agents[agent_id]["followed_json"])
                if target_id not in following:
                    following.append(target_id)
                    db.execute("UPDATE agents SET followed_json=? WHERE run_id=? AND id=?", (json.dumps(following), run_id, agent_id))
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", (run_id, event_id, round_number, agent_id, action_type, target_id, content.strip() or None, json.dumps(payload, ensure_ascii=False), timestamp))
        status = "complete" if round_number >= run["total_rounds"] else "running"
        db.execute("UPDATE runs SET current_round=?,status=?,updated_at=? WHERE id=?", (round_number, status, timestamp, run_id))
        return {"run_id": run_id, "round_completed": round_number, "total_rounds": run["total_rounds"], "actions_recorded": len(actions), "status": status}


def report_data(workspace: Path, run_id: str) -> dict[str, Any]:
    with connect(workspace) as db:
        run = run_row(db, run_id)
        agents = [dict(row) for row in db.execute("SELECT id,name,profile_json,followed_json,communities_json FROM agents WHERE run_id=? ORDER BY id", (run_id,))]
        posts = [dict(row) for row in db.execute("SELECT * FROM posts WHERE run_id=? ORDER BY round,id", (run_id,))]
        comments = [dict(row) for row in db.execute("SELECT * FROM comments WHERE run_id=? ORDER BY round,id", (run_id,))]
        events = [dict(row) for row in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY round,created_at,id", (run_id,))]
        for agent in agents:
            agent["profile"] = json.loads(agent.pop("profile_json"))
            agent["following"] = json.loads(agent.pop("followed_json"))
            agent["communities"] = json.loads(agent.pop("communities_json"))
        for event in events:
            event["payload"] = json.loads(event.pop("payload_json"))
        totals: dict[str, int] = {}
        for event in events:
            totals[event["action_type"]] = totals.get(event["action_type"], 0) + 1
        stats = []
        for agent in agents:
            authored_posts = sum(1 for post in posts if post["author_id"] == agent["id"])
            authored_comments = sum(1 for comment in comments if comment["author_id"] == agent["id"])
            authored_content = {post["id"] for post in posts if post["author_id"] == agent["id"]} | {comment["id"] for comment in comments if comment["author_id"] == agent["id"]}
            engagement = sum(1 for event in events if event["action_type"] in {"upvote", "downvote", "like", "repost"} and event["target_id"] in authored_content)
            stats.append({"agent_id": agent["id"], "name": agent["name"], "posts": authored_posts, "comments": authored_comments, "following": len(agent["following"]), "engagement_received": engagement})
        return {
            "run": {key: run[key] for key in run.keys()}, "agents": agents, "posts": posts,
            "comments": comments, "events": events, "action_totals": totals,
            "agent_stats": stats,
            "note": "All actions are generated by Codex for synthetic personas. They are not observations of real people or predictions.",
        }


def simulation_visualize(workspace: Path, run_id: str, output: str | None = None) -> dict[str, Any]:
    payload = report_data(workspace, run_id)
    if output:
        output_path = Path(output).expanduser()
        if not output_path.is_absolute():
            output_path = workspace / output_path
        output_path = output_path.resolve()
        if output_path.suffix.lower() != ".html":
            fail("Visualization output must be an HTML file.")
    else:
        output_path = data_dir(workspace) / "runs" / run_id / "visualization.html"

    template_path = Path(__file__).with_name("visualizer_template.html")
    try:
        template = template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"Visualization template is missing: {template_path}")
    placeholder = "__FLOCK_DATA__"
    if template.count(placeholder) != 1:
        fail(f"Visualization template must contain exactly one {placeholder} placeholder.")

    embedded_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for character, replacement in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        embedded_data = embedded_data.replace(character, replacement)
    document = template.replace(placeholder, embedded_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(document, encoding="utf-8")
    temporary_path.replace(output_path)
    return {
        "run_id": run_id,
        "visualization": str(output_path),
        "self_contained": True,
        "external_requests": 0,
        "agents": len(payload["agents"]),
        "events": len(payload["events"]),
        "current_round": payload["run"]["current_round"],
        "total_rounds": payload["run"]["total_rounds"],
    }


def save_report(workspace: Path, run_id: str, report_file: Path) -> dict[str, Any]:
    content = report_file.read_text(encoding="utf-8")
    if not content.strip():
        fail("Report file is empty.")
    with connect(workspace) as db:
        run_row(db, run_id)
        db.execute("INSERT INTO reports(run_id,markdown,updated_at) VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE SET markdown=excluded.markdown,updated_at=excluded.updated_at", (run_id, content, now()))
    report_path = data_dir(workspace) / "runs" / run_id / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    return {"run_id": run_id, "report": str(report_path), "characters": len(content)}


def run_list(workspace: Path) -> list[dict[str, Any]]:
    with connect(workspace) as db:
        return [dict(row) for row in db.execute("SELECT id,title,platform,total_rounds,current_round,status,created_at FROM runs ORDER BY created_at DESC")]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Flock workspace graph and simulation helper (no model/API calls).")
    root.add_argument("--workspace", default=".", help="Codex workspace directory; defaults to current directory")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a Flock graph database in .flock/")
    init.add_argument("--name", default="Flock project")

    graph = commands.add_parser("graph", help="Inspect or update the knowledge graph")
    graph_commands = graph.add_subparsers(dest="graph_command", required=True)
    validate = graph_commands.add_parser("validate")
    validate.add_argument("--input", required=True)
    graph_import = graph_commands.add_parser("import", help="Import or merge a graph JSON file")
    graph_import.add_argument("--input", required=True)
    graph_commands.add_parser("stats")
    search = graph_commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=25)
    mermaid = graph_commands.add_parser("mermaid")
    mermaid.add_argument("--limit", type=int, default=80)
    export = graph_commands.add_parser("export")
    export.add_argument("--output", required=True)

    simulation = commands.add_parser("simulation", help="Manage simulation specs, rounds, and reports")
    sim_commands = simulation.add_subparsers(dest="simulation_command", required=True)
    sim_validate = sim_commands.add_parser("validate")
    sim_validate.add_argument("--spec", required=True)
    sim_create = sim_commands.add_parser("create")
    sim_create.add_argument("--spec", required=True)
    for name in ("status", "prompt", "report-data"):
        command = sim_commands.add_parser(name)
        command.add_argument("--id", required=True)
    advance = sim_commands.add_parser("advance")
    advance.add_argument("--id", required=True)
    advance.add_argument("--actions", required=True)
    report = sim_commands.add_parser("save-report")
    report.add_argument("--id", required=True)
    report.add_argument("--input", required=True)
    visualize = sim_commands.add_parser("visualize", help="Create a self-contained interactive HTML view of a run")
    visualize.add_argument("--id", required=True)
    visualize.add_argument("--output", help="HTML output path; defaults to .flock/runs/<run_id>/visualization.html")
    sim_commands.add_parser("list")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        workspace = workspace_path(args.workspace)
        if args.command == "init":
            result = initialize(workspace, args.name)
        elif args.command == "graph":
            if args.graph_command == "validate":
                graph = validate_graph(read_json(Path(args.input).expanduser().resolve()))
                result = {"valid": True, "sources": len(graph.get("sources", [])), "entities": len(graph.get("entities", [])), "relationships": len(graph.get("relationships", []))}
            elif args.graph_command == "import":
                result = import_graph(workspace, Path(args.input).expanduser().resolve())
            elif args.graph_command == "stats":
                result = graph_stats(workspace)
            elif args.graph_command == "search":
                if args.limit < 1 or args.limit > 500:
                    fail("Search limit must be between 1 and 500.")
                result = graph_search(workspace, args.query, args.limit)
            elif args.graph_command == "mermaid":
                if args.limit < 1 or args.limit > 300:
                    fail("Mermaid node limit must be between 1 and 300.")
                result = {"mermaid": graph_mermaid(workspace, args.limit)}
            else:
                with connect(workspace) as db:
                    result = graph_as_json(db)
                write_json(Path(args.output).expanduser().resolve(), result)
                result = {"exported": args.output, "entities": len(result["entities"]), "relationships": len(result["relationships"])}
        elif args.command == "simulation":
            if args.simulation_command == "validate":
                spec = validate_spec(read_json(Path(args.spec).expanduser().resolve()))
                result = {"valid": True, "title": spec["title"], "platform": spec["platform"], "agents": len(spec["agents"]), "rounds": spec["rounds"]}
            elif args.simulation_command == "create":
                result = create_run(workspace, Path(args.spec).expanduser().resolve())
            elif args.simulation_command == "status":
                result = run_status(workspace, args.id)
            elif args.simulation_command == "prompt":
                result = simulation_prompt(workspace, args.id)
            elif args.simulation_command == "advance":
                result = advance_run(workspace, args.id, Path(args.actions).expanduser().resolve())
            elif args.simulation_command == "report-data":
                result = report_data(workspace, args.id)
            elif args.simulation_command == "save-report":
                result = save_report(workspace, args.id, Path(args.input).expanduser().resolve())
            elif args.simulation_command == "visualize":
                result = simulation_visualize(workspace, args.id, args.output)
            else:
                result = run_list(workspace)
        else:
            fail("Unknown command.")
        emit(result)
        return 0
    except (FlockError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"flock: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
