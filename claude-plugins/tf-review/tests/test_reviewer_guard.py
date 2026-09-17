"""Tests for hooks/reviewer_guard.py.

Run: python3 -m unittest discover -s claude-plugins/tf-review/tests -v
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[1] / "hooks" / "reviewer_guard.py"
sys.path.insert(0, str(GUARD.parent))
import reviewer_guard  # noqa: E402


def run_hook(payload):
    proc = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["hookSpecificOutput"] if proc.stdout.strip() else None


class BashAllowlistTest(unittest.TestCase):
    def test_read_only_commands_pass(self):
        for command in (
            "git log --oneline -20",
            "git --no-pager show HEAD~1:src/app.ts",
            "git -C /repo/.tf-review/pr-4/tree blame -L 10,40 src/app.ts",
            "git diff 5fe7856 8589c97 -- src/app.ts | head -100",
            "git grep -n 'sanitizeTiers' -- src",
            "rg -n 'router\\.(get|post)' src 2>/dev/null",
            "grep -E 'a|b' src/app.ts",
            "cd /repo && git log -p -- src/a.ts 2>&1 | head -50",
            "find src -name '*.ts' -newer package.json",
            "git log --format='%h %s' | sort -k2 | uniq -c",
            "sort -rn -k1,1 counts.txt",
            "cat src/app.ts; wc -l src/app.ts",
            "git branch -a",
        ):
            with self.subTest(command=command):
                self.assertIsNone(reviewer_guard.check_bash(command))

    def test_writing_or_executing_commands_are_denied(self):
        for command in (
            "rm -rf src",
            "npm test",
            "python3 -c 'print(1)'",
            "curl https://example.com",
            "cat src/app.ts > /tmp/leak",
            "echo hi >> review.md",
            "git log --output=/tmp/x",
            "git -c core.pager=sh log",
            "git checkout main",
            "git branch -D main",
            "git branch --set-upstream-to=origin/x",
            "git grep -Oless foo",
            "find . -name x -delete",
            "find . -exec rm {} ;",
            "rg --pre ./run.sh foo",
            "sort -o out.txt in.txt",
            "sort -uo /tmp/out src/app.ts",
            "sort --compress-program=sh in.txt",
            "uniq src/app.ts /tmp/out",
            "sed -n -e 1p -e 'w /tmp/out' src/app.ts",
            "sed -n '10,40p' src/app.ts",
            "cat src/app.ts#; rm -rf src",
            "git log#|sh",
            "git grep -nOless foo",
            "file -C -m magic",
            "cat a&rm -rf src",
            "cat a |& sh",
            "cat <<< x",
            "{ rm -rf src; }",
            "echo $(whoami)",
            "cat `ls`",
            "diff <(git show a:x) x",
            "git log &",
            "GIT_EXTERNAL_DIFF=./x git diff",
            "git log\nrm -rf src",
            "xargs rm < files.txt",
            "git log | sh",
            "rg --hostname-bin=./x --hyperlink-format=default foo",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(reviewer_guard.check_bash(command))


class HookProtocolTest(unittest.TestCase):
    def test_reviewer_bash_is_auto_allowed_or_denied(self):
        allowed = run_hook({"agent_type": "tf-review:full-reviewer", "tool_name": "Bash",
                            "tool_input": {"command": "git log -5"}})
        self.assertEqual(allowed["permissionDecision"], "allow")
        denied = run_hook({"agent_type": "tf-review:incremental-reviewer", "tool_name": "Bash",
                           "tool_input": {"command": "gh pr merge 4"}})
        self.assertEqual(denied["permissionDecision"], "deny")
        self.assertIn("read-only", denied["permissionDecisionReason"])

    def test_reviewer_writes_only_review_md(self):
        ok = run_hook({"agent_type": "tf-review:full-reviewer", "tool_name": "Write",
                       "tool_input": {"file_path": "/repo/.tf-review/pr-12/review.md", "content": "x"}})
        self.assertEqual(ok["permissionDecision"], "allow")
        for path in ("/repo/src/app.ts", "/repo/.tf-review/pr-12/context.md", "/repo/review.md",
                     "/repo/.tf-review/pr-12/review.md.bak"):
            with self.subTest(path=path):
                result = run_hook({"agent_type": "tf-review:full-reviewer", "tool_name": "Edit",
                                   "tool_input": {"file_path": path}})
                self.assertEqual(result["permissionDecision"], "deny")

    def test_other_agents_and_main_session_are_untouched(self):
        for agent_type in (None, "general-purpose", "full-reviewer"):
            with self.subTest(agent_type=agent_type):
                self.assertIsNone(run_hook({"agent_type": agent_type, "tool_name": "Bash",
                                            "tool_input": {"command": "rm -rf /tmp/x"}}))
        self.assertIsNone(run_hook({"agent_type": "tf-review:full-reviewer", "tool_name": "Read",
                                    "tool_input": {"file_path": "/repo/src/app.ts"}}))

    def test_reviewer_cannot_escape_through_other_tools(self):
        for tool in ("WebFetch", "WebSearch", "Agent", "Task", "Skill", "mcp__computer-use__type"):
            with self.subTest(tool=tool):
                result = run_hook({"agent_type": "tf-review:incremental-reviewer", "tool_name": tool,
                                   "tool_input": {}})
                self.assertEqual(result["permissionDecision"], "deny")

    def test_hook_matcher_covers_escape_tools(self):
        import re
        hooks = json.loads((GUARD.parent / "hooks.json").read_text())["hooks"]["PreToolUse"]
        matcher = re.compile(f"^(?:{hooks[0]['matcher']})$")
        for tool in ("Bash", "Write", "Edit", "WebFetch", "Agent", "Task", "Skill", "mcp__chrome-devtools__click"):
            self.assertTrue(matcher.match(tool), tool)
        for tool in ("Read", "Grep", "Glob"):
            self.assertFalse(matcher.match(tool), tool)


if __name__ == "__main__":
    unittest.main()
