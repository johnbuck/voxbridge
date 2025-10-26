---
description: Show test coverage stats and identify gaps
---

Run tests with coverage analysis and display current coverage statistics to identify areas needing improvement.

Execute the following command to view coverage:

```bash
./test.sh tests/unit --cov=src --cov-report=term-missing --cov-report=html
```

This will:
- Run all unit tests in `tests/unit/`
- Generate coverage report for `src/` directory
- Display terminal output with missing lines
- Create HTML report in `htmlcov/` directory

**Expected output:**

```
========================= test session starts ==========================
collected 43 items

tests/unit/test_audio_receiver.py ............... [ 35%]
tests/unit/test_discord_bot_api.py ...................... [ 86%]
tests/unit/test_speaker_manager.py .... [100%]

---------- coverage: platform linux, python 3.11.0-final-0 -----------
Name                        Stmts   Miss  Cover   Missing
---------------------------------------------------------
src/discord_bot.py            520    XXX    XX%   (varies)
src/speaker_manager.py        412    XXX    XX%   (varies)
src/streaming_handler.py      298    XXX    XX%   (varies)
src/whisper_client.py         178    XXX    XX%   (varies)
src/whisper_server.py         245    XXX    XX%   (varies)
---------------------------------------------------------
TOTAL                        1653    XXX    88%

========================== 38 passed, 5 failed in 0.40s ==========================

Wrote HTML coverage report to htmlcov/index.html
```

**Note**: Current test status is 43 tests total (38 passing, 5 failing), with 88% overall coverage.

**Interpreting results:**

- **Stmts**: Total statements in the file
- **Miss**: Number of uncovered statements
- **Cover**: Coverage percentage
- **Missing**: Line numbers that are not covered

**Target:** 90%+ coverage (currently at 88%)

**Current Status:**
- **Overall**: 88% coverage ✅ (exceeded 80% target)
- **Tests**: 43 total (38 passing, 5 failing)
- **Priority**: Fix 5 failing speaker_manager tests to reach 100% pass rate

**To view detailed HTML report:**

```bash
# macOS
open htmlcov/index.html

# Linux
xdg-open htmlcov/index.html

# Or navigate directly to:
file:///home/wiley/Docker/voxbridge/htmlcov/index.html
```

**HTML report features:**
- Click on any file to see line-by-line coverage
- Red lines: Not covered (need tests)
- Green lines: Covered by tests
- Yellow lines: Partially covered (some branches not tested)

**Next steps:**

1. **Identify priority gaps:**
   ```bash
   # View coverage for specific module
   open htmlcov/speaker_manager_py.html
   ```

2. **Use test-reviewer agent:**
   ```
   /agents test-reviewer

   Analyze coverage for speaker_manager.py and recommend improvements.
   ```

3. **Write missing tests:**
   ```
   /agents unit-test-writer

   Write unit tests for speaker_manager.py lines 450-475 to increase coverage.
   ```

4. **Verify improvements:**
   ```bash
   # Run coverage again
   ./test.sh tests/unit --cov=src --cov-report=term-missing

   # Compare before/after
   ```

**Coverage by test type:**

```bash
# Unit tests only (fast, isolated)
./test.sh tests/unit --cov=src --cov-report=term

# Integration tests only (component interactions)
./test.sh tests/integration --cov=src --cov-report=term

# All tests (comprehensive)
./test.sh tests/unit tests/integration --cov=. --cov-report=html
```

**Troubleshooting:**

**If coverage report not generated:**
- Ensure pytest-cov is installed: `pip install pytest-cov`
- Check that `./test.sh` script exists and is executable

**If coverage seems incorrect:**
- Clear old coverage data: `rm .coverage htmlcov/* -rf`
- Re-run tests with `--cov-report=term-missing` for details
- Verify source paths are correct (should be `src/`)

**Current coverage status:**

| Metric                 | Current | Target | Status   |
|------------------------|---------|--------|----------|
| **Overall Coverage**   | **88%** | **90%**| 🟡 Close |
| **Passing Tests**      | **38/43**| **43/43**| 🔴 5 failing |
| **Test Categories**    | Unit, Integration, E2E | All | ✅ Complete |

**Priority**: Fix 5 failing speaker_manager tests to achieve 100% pass rate
