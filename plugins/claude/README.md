# Flock for Claude Code

This native Claude Code plugin packages the Flock skill and local Python helper. Claude Code supplies reasoning in the user's active session; the helper validates and stores graph and simulation data locally under `.flock/`.

## Install

Add this repository as a Claude Code marketplace and install Flock:

```text
/plugin marketplace add plilian/flock
/plugin install flock@flock
```

Alternatively, run the equivalent `claude plugin marketplace add plilian/flock` and `claude plugin install flock@flock` commands in a terminal.

Open a workspace and ask Claude to use Flock. Python 3.11+ must be available in Claude Code's execution environment.

Flock does not request or store provider API keys. Claude account access, plan limits, and data policies remain controlled by Anthropic and the user's Claude Code setup. Simulation results are synthetic explorations, not forecasts.
