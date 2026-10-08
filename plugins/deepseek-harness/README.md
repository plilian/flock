# Flock for DeepSeek Harness

This is a native DeepSeek Harness bundle that registers the Flock skill in a Harness profile. It uses the active Harness agent for model reasoning and the bundled Python helper for local graph and run storage.

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
