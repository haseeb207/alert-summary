#!/usr/bin/env bash
# Run the Datadog alert agent using the project's virtualenv (no need to activate).
# Usage: ./run_agent.sh   (from the email-agent directory)

set -e
cd "$(dirname "$0")"

if [ -x "venv/bin/python" ]; then
  exec venv/bin/python agent.py "$@"
elif [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python agent.py "$@"
else
  echo "No venv found. Create one with: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
  exec python3 agent.py "$@"
fi
