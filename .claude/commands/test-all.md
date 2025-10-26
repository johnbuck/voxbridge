---
description: Run full test suite with HTML coverage report
---

Run the complete VoxBridge test suite (unit + integration) with comprehensive coverage analysis.

Execute the following command to run all tests and generate an HTML coverage report:

```bash
./test.sh tests/unit tests/integration --cov=. --cov-report=html --cov-report=term
```

This will:
- Run all unit tests (`tests/unit/`)
- Run all integration tests (`tests/integration/`)
- Generate coverage report for entire project
- Create HTML coverage report in `htmlcov/` directory
- Display terminal coverage summary

Expected output:
- All test results (unit + integration)
- Coverage percentage for each module
- HTML report location

**After completion:**
- Open coverage report: `open htmlcov/index.html` (macOS) or `xdg-open htmlcov/index.html` (Linux)
- Browse interactive coverage visualization

**Note:** Full test suite takes ~1-2 minutes to complete.
