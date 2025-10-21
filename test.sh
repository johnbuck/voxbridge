#!/usr/bin/env bash
# Test runner wrapper for VoxBridge
# Usage: ./test.sh [pytest args]

docker compose -f docker-compose.test.yml run --rm test pytest "$@"
