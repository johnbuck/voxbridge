---
description: Run unit tests with coverage report
---

Run VoxBridge unit tests with code coverage analysis.

Execute the following command to run all unit tests with detailed coverage reporting:

```bash
./test.sh tests/unit -v --cov=src --cov-report=term-missing
```

This will:
- Run all tests in the `tests/unit/` directory
- Show verbose output (`-v`)
- Generate coverage report for `src/` directory
- Display which lines are missing coverage

Expected output:
- Test results with pass/fail status
- Coverage percentage for each module
- Lines not covered by tests

**Note:** Unit tests are fast (fully mocked, no external dependencies) and should complete in <10 seconds.
