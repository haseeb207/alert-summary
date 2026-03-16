#!/bin/bash

# Test the agent in DRY RUN mode — processes alerts without posting to Teams.
# The agent runs for a limited time then shuts down automatically.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

AGENT_TIMEOUT=30  # seconds to let the agent run before stopping it

echo "🧪 TEST MODE: Running agent with DRY_RUN enabled"
echo "=================================================="
echo ""

# Clean up old database & pid file
echo "1️⃣  Cleaning up old database..."
rm -f alerts.db agent.pid
echo "   ✅ Database cleaned"
echo ""

OUTPUT_FILE="test_output.log"
echo "2️⃣  Running agent in DRY RUN mode for ${AGENT_TIMEOUT}s (output saved to $OUTPUT_FILE)..."
echo ""

# Force DRY_RUN on for this test
export DRY_RUN=true

# Run agent in background, kill after timeout
./venv/bin/python agent.py > >(tee "$OUTPUT_FILE") 2>&1 &
AGENT_PID=$!

sleep "$AGENT_TIMEOUT"
echo ""
echo "⏱️  Timeout reached — stopping agent (PID $AGENT_PID)..."
kill "$AGENT_PID" 2>/dev/null || true
wait "$AGENT_PID" 2>/dev/null || true

echo ""
echo "=================================================="
echo "✅ TEST COMPLETE"
echo "=================================================="
echo ""
echo "📋 Output saved to: $OUTPUT_FILE"
echo ""
echo "📝 Review the output above to see:"
echo "   - Alerts processed from watch directory"
echo "   - Aggregation by the configured period (AGGREGATION_PERIOD in .env)"
echo "   - What would be posted to Teams (in DRY RUN format)"
echo ""
echo "🔄 Next steps:"
echo "   1. Review the output to verify it looks correct"
echo "   2. When ready, change DRY_RUN=false in .env"
echo "   3. Run: ./venv/bin/python agent.py"
echo "   4. Alerts will then be posted to Teams"
echo ""
