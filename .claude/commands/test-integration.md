---
description: Run integration tests with mock servers
---

Run VoxBridge integration tests using mock external services.

Execute the following command to run all integration tests:

```bash
./test.sh tests/integration -v
```

This will:
- Run all tests in the `tests/integration/` directory
- Start mock servers (WhisperX, n8n, Chatterbox, Discord)
- Show verbose output (`-v`)
- Test component interactions

Expected output:
- Mock server startup logs
- Integration test results with pass/fail status
- Latency benchmarks (if applicable)

**Note:** Integration tests take longer (~30-60 seconds) as they test full component interactions with mock servers.

**Requirements:** None - mock servers are automatically started by the test framework.
