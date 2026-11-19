verdict: approve
public_api: no
behaviour_change: yes
fails_without_fix: yes

# PR review T-pymodaq_utils-M02 r1
branch: agent/pymodaq_utils/refactor-threadcommand/2026-11-19 (1 commit d1468b3b3, +9/-1, 2 files)
previous review: none (r1)

## Checks
1. Task match: OK. packages/pymodaq_utils/src/pymodaq_utils/utils.py:369-370 turns `self.attribute = attribute` into the `else` branch, exactly as the task block says; one test added in packages/pymodaq_utils/tests/utils_test.py:142-147. No other edits, no reformatting.
2. Correctness: OK. Read ThreadCommand.__init__/__eq__/serialize/deserialize whole. When attribute is given (or both are None) the result is the same as before. When only attributes= is given, .attribute now holds the value instead of None. deserialize calls ThreadCommand(command, attribute, ...) positionally, so it never takes the deprecated path. Grep over packages/: no caller passes attributes= and nothing reads .attributes outside utils.py:368.
3. Behaviour/API: the signature, defaults and the DeprecationWarning (warnings.py:7, stacklevel 3) do not change. .attributes is still set on the deprecated path, so plugins that read it keep working. The one behaviour change is the intended fix: .attribute is no longer None after attributes=. It also changes __eq__ and serialize results for such objects, which is correct now. No public name is added or removed, so hard rule 1 is not involved.
4. Tests: I copied the branch's utils_test.py to tests/utils_review_tmp_test.py and ran it against dev_agent code (`-k ThreadCommand`, py3.14 env). test_ThreadCommand_deprecated_attributes FAILS (`assert None == [1, 2]`) and the other 10 pass. I then deleted the file and `git status` is clean. The test asserts exact values for both .attribute and .attributes and checks the warning with pytest.warns(DeprecationWarning). On branch code it passes according to the caller's "CI green". I did not re-run it locally on branch code (unverified locally).
5. Docs: the class docstring ("attributes: deprecated, attribute should be used instead") matches the code. The commit message is accurate.

## Findings
- none blocking.
- packages/pymodaq_utils/src/pymodaq_utils/utils.py:365 (nit, out of scope): if both attribute and attributes are passed, attributes is still silently dropped without a warning. This was already so before the PR and the task does not ask to change it.

summary: Fix ThreadCommand dropping the value passed through the deprecated `attributes=` keyword (it was overwritten with None), with a regression test that fails without the fix.
