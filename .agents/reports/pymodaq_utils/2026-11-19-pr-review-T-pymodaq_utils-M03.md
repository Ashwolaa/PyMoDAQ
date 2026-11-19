verdict: approve
public_api: no
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-M03 (branch agent/pymodaq_utils/refactor-socket/2026-11-19, commit 79df7b849)

## 1. Task match
- packages/pymodaq_utils/src/pymodaq_utils/mysocket.py:98-101: raises ConnectionError on an empty recv(), as the task block asks.
- packages/pymodaq_utils/tests/mysocket_test.py:1-41: new fake-socket test file, as the task block asks.
- mysocket.py:80-86: a "Raises" docstring section was added. It documents the change and is in scope. No untouched lines were reformatted. Diff is 52 added lines, under the 300 cap.
- serialize/mysocket.py:29 (SocketString) is untouched, as the plan note says. serialize.mysocket.Socket subclasses the base Socket and inherits the fix (checked, serialize/mysocket.py:64).

## 2. Correctness
- mysocket.py:93-103: on a real socket an empty read only happens when the peer closed (or on a 0-byte request, and the loop guard `mess_length < length` rules that out), so the new condition cannot fire on a live connection.
- length <= 0: the loop never runs and b'' is returned as before.
- Callers: no caller in packages/ calls the network Socket.check_received_length / get_first_nbytes / check_receiving (grep). serializer_legacy.py uses the same method name on SocketString, which this change does not touch. External plugins are unverified.

## 3. Behaviour and API
- No name, signature, default or return value changes. One behaviour change: a closed peer now raises ConnectionError (an OSError subclass) where the loop used to spin forever at 100% CPU. Code that already catches OSError/socket errors handles it. It replaces a hang, so hard rule 1 is not affected.

## 4. Tests
- I ran the branch test file as tests/mysocket_review_tmp_test.py against dev_agent code, each test under `timeout 60`:
  test_chunked_happy_path PASS, test_length_not_int PASS,
  test_peer_closed_raises HANG (killed by timeout), test_peer_closed_immediately_raises HANG (killed by timeout).
  So both bug tests fail without the fix. The temp file is deleted and git status is clean apart from other reviewers' reports.
- On the branch code (git archive): all 4 pass. Full pymodaq_utils suite: 310 passed, 3 skipped, 1 failed (config_test.py::test_nested_update_from_user, already failing on dev_agent).
- mysocket_test.py:28,31: exact checks (payload equality, match="5 bytes out of 10"). mysocket_test.py:35 only checks the exception type, which is enough for that case.
- Minor, not blocking: the tests use a fake socket, so the 4096-byte branch is covered (10240-byte payload) but no real socketpair is used.

## 5. Docs
- mysocket.py:81-86: the TypeError and ConnectionError entries match the code. The commit message claim ("spin forever") is confirmed by the timeouts above.

## Checks
- flake8 blocking selection: 0 errors on the branch.
- ruff format --check: mysocket_test.py is formatted. mysocket.py "would be reformatted", but it already fails on dev_agent. The new lines follow the file's single-quote style, and reformatting the whole file would break hard rule 5. Not a blocker.
- Unverified: Qt backend matrix (irrelevant, no Qt code) and layering_test (no imports changed).

summary: Socket.check_received_length now raises ConnectionError instead of looping forever when the peer closes mid-message; new fake-socket tests hang on dev_agent and pass with the fix.
