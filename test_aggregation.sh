#!/bin/bash
cd /Users/haseeb.ahmedjaved/Downloads/ai-agents/email-agent

# Run agent in background
source venv/bin/activate
python agent.py > /tmp/agent_test.log 2>&1 &
AGENT_PID=$!

# Wait 90 seconds
echo "Agent running (PID: $AGENT_PID)"
for i in {1..9}; do
  echo "Waiting... $((i*10))s"
  sleep 10
done

# Kill agent
kill $AGENT_PID 2>/dev/null
sleep 2

# Check database
echo ""
echo "=== Database Status ==="
python3 verify_db.py

echo ""
echo "=== Recent Agent Logs ==="
tail -30 /tmp/agent_test.log
