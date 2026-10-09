# Flock for DeepSeek Harness

This is a native DeepSeek Harness bundle that registers the Flock skill in a Harness profile. It uses the active Harness agent for model reasoning and the bundled Python helper for local evidence-labeled graph, audit, and experiment storage.

DeepSeek Harness is a developer-preview host. This integration does not target the DeepSeek chat website or DeepSeek API. Model access follows the provider and account configuration in DeepSeek Harness; Flock does not request or store those credentials.

## Install from a repository checkout

Requirements: DeepSeek Harness with the `web` profile, Python 3.11+, and workspace/terminal access.

```bash
git clone https://github.com/plilian/flock.git
cd flock
dsh plugin --profile web add ./plugins/deepseek-harness
```

Restart the Harness profile if it does not hot-reload the installed skill. In a workspace, invoke `/flock` or ask the agent to use Flock. Graphs and simulations stay under `.flock/` in the selected workspace.

Uninstall with:

```bash
dsh plugin --profile web remove flock-deepseek-harness
```

Ask the active agent to audit source references or compare a baseline with controlled scenario variants. Scenario Lab runs each variant independently from the same synthetic roster and produces a local comparison view under `.flock/experiments/`.

The Flock skill supports English, Japanese, Simplified Chinese, and Spanish. It follows the user's language for natural-language work and reports while keeping required commands and data-schema values unchanged.
