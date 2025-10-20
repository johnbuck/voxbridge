#!/bin/bash
# VoxBridge Test Runner
#
# Usage: ./test.sh [pytest arguments]
#
# Examples:
#   ./test.sh                              # Run all tests
#   ./test.sh tests/unit -v                # Unit tests verbose
#   ./test.sh tests/unit -k "connect"      # Tests matching "connect"
#   ./test.sh --cov --cov-report=html      # With coverage
#   ./test.sh tests/unit --pdb             # Debug mode
#
# Common pytest options:
#   -v, --verbose          # More detailed output
#   -s                     # Show print statements
#   -x                     # Stop on first failure
#   -k "pattern"           # Run tests matching pattern
#   --pdb                  # Drop into debugger on failure
#   -m marker              # Run tests with specific marker
#   --cov=.                # Coverage report
#   --lf                   # Run last failed tests
#   --tb=short             # Short traceback format

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     🧪 VoxBridge Test Runner           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Build test container if needed
echo -e "${BLUE}📦 Building test container...${NC}"
docker compose -f docker-compose.test.yml build test

echo ""
echo -e "${BLUE}🚀 Running tests...${NC}"
echo -e "${YELLOW}   Arguments: ${@:-"(default: all tests)"}${NC}"
echo ""

# Run tests
# Pass all arguments to pytest, or use default if none provided
if [ $# -eq 0 ]; then
    # No arguments - run all tests with default settings
    docker compose -f docker-compose.test.yml run --rm test
else
    # Arguments provided - pass them to pytest explicitly
    docker compose -f docker-compose.test.yml run --rm test pytest "$@"
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Tests failed (exit code: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
