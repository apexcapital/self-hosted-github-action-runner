#!/usr/bin/env bash

# GitHub Actions Runner Orchestrator Monitoring Script
# This script continuously monitors the orchestrator and runner status

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "\n${BLUE}=== $(date) ===${NC}"
    
    # Get orchestrator status
    echo -e "${BLUE}Orchestrator Status:${NC}"
    if status=$(curl -s http://localhost:8080/api/v1/status 2>/dev/null); then
        echo "$status" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    runners = data['runners']
    queue = data['queue']
    
    print(f\"  Active Runners: {runners['active']}\")
    print(f\"  Registered: {runners['registered_running']}\")
    print(f\"  Unregistered: {runners['unregistered_running']}\")
    print(f\"  Queue Length: {queue['current_length']}\")
    print(f\"  Total Created: {runners['total_created']}\")
    print(f\"  Total Destroyed: {runners['total_destroyed']}\")
    
    # Alert conditions
    if runners['unregistered_running'] > 0:
        print('  ⚠️  WARNING: Unregistered runners found!')
    if runners['active'] > 10:
        print('  🚨 ALERT: Too many runners!')
    if runners['active'] >= 2:
        print('  ✅ Good: Minimum runners maintained')
        
except Exception as e:
    print(f'  ❌ Error parsing status: {e}')
"
    else
        echo -e "  ${RED}❌ Cannot reach orchestrator API${NC}"
    fi
    
    # Get Docker container status
    echo -e "\n${BLUE}Docker Containers:${NC}"
    runner_count=$(docker ps --filter "name=github-runner-" --format "table {{.Names}}" | grep -v NAMES | wc -l)
    echo "  Runner containers: $runner_count"
    
    if [ "$runner_count" -gt 10 ]; then
        echo -e "  ${RED}🚨 ALERT: Too many containers!${NC}"
    elif [ "$runner_count" -ge 2 ]; then
        echo -e "  ${GREEN}✅ Normal container count${NC}"
    else
        echo -e "  ${YELLOW}⚠️  Below minimum containers${NC}"
    fi
    
    # Check for any error conditions
    if docker logs orchestrator --tail 10 2>/dev/null | grep -q "circuit breaker"; then
        echo -e "  ${RED}🚨 CIRCUIT BREAKER ACTIVE${NC}"
    fi
    
    echo "  ────────────────────────────────────────"
}

# Main monitoring loop
echo -e "${GREEN}Starting Orchestrator Monitoring...${NC}"
echo "Press Ctrl+C to stop"

while true; do
    print_status
    sleep 30
done
