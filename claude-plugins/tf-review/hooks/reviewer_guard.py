#!/usr/bin/env python3
"""PreToolUse guard for the tf-review reviewer agents.

The reviewers read text written by other people (PR description, diff, earlier
reviews), so their tool use is enforced here instead of trusted to the prompt:

- Bash: only single-line, read-only commands from an allowlist (git history,
  search and file viewers). Allowed commands are auto-approved, so the review
  runs without permission prompts; everything else is denied.
- Write / Edit: only `.tf-review/pr-<n>/review.md`.
- Anything else routed here (web, MCP, nested agents, skills): denied.

Tool calls outside these agents are left alone (no output, exit 0).
"""
import json
import re
import shlex
import sys

REVIEWER_AGENTS = {"tf-review:full-reviewer", "tf-review:incremental-reviewer"}
REVIEW_FILE_RE = re.compile(r"(^|/)\.tf-review/pr-\d+/review\.md$")
SEPARATORS = {";", "&&", "||", "|"}
SAFE_COMMANDS = {
    "rg", "grep", "egrep", "fgrep", "cat", "head", "tail", "wc", "ls", "find", "sort", "uniq", "cut", "tr",
    "nl", "stat", "pwd", "echo", "printf", "basename", "dirname", "realpath", "jq", "diff", "column", "true", "cd",
}
GIT_READ_ONLY = {
    "log", "show", "blame", "diff", "grep", "ls-files", "ls-tree", "rev-parse", "cat-file", "merge-base",
    "shortlog", "status", "describe", "name-rev", "rev-list", "branch", "tag",
}
# Options that make an otherwise read-only command write files or run programs:
# long options (exact or `--opt=value`) and short option letters, also inside bundles like `-uo`.
DENIED_LONG = {
    "git": ("--output", "--ext-diff", "--open-files-in-pager", "--textconv", "--delete", "--move",
            "--set-upstream-to", "--unset-upstream", "--edit-description"),
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "rg": ("--pre", "--pre-glob", "--hostname-bin"),
    "sort": ("--output", "--compress-program"),
}
DENIED_SHORT = {"git": "O", "sort": "o"}


def decision(kind, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                   "permissionDecisionReason": reason}}


def check_command(argv):
    """Return None if `argv` (one simple command) is read-only, else the reason it is not."""
    name = argv[0]
    if "=" in name:
        return "environment assignments are not allowed"
    if name not in SAFE_COMMANDS and name != "git":
        return f"`{name}` is not an allowed read-only command"
    args = argv[1:]
    for arg in args:
        if any(arg == opt or arg.startswith(opt + "=") for opt in DENIED_LONG.get(name, ())):
            return f"`{name} {arg}` can write files or run programs"
        if (arg.startswith("-") and not arg.startswith("--") and name != "find"
                and set(arg[1:]) & set(DENIED_SHORT.get(name, ""))):
            return f"`{name} {arg}` can write files or run programs"
    if name == "uniq" and any(not a.startswith("-") for a in args):
        return "`uniq` may only read stdin (its second argument is an output file)"
    if name == "git":
        rest = list(args)
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in ("-C",) and rest:
                rest.pop(0)
            elif flag not in ("--no-pager", "-P"):
                return f"`git {flag}` is not allowed"
        if not rest or rest[0] not in GIT_READ_ONLY:
            return f"`git {rest[0] if rest else ''}` is not a read-only git command"
        if rest[0] in ("branch", "tag") and len(rest) > 1 and not all(a.startswith("-") for a in rest[1:]):
            return "git branch/tag may only list"
    return None


def check_bash(command):
    if "\n" in command or "\r" in command:
        return "multi-line commands are not allowed; run one command per call"
    if "`" in command or "$(" in command or "<(" in command or ">(" in command:
        return "command substitution is not allowed"
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # bash only starts a comment at a word boundary; never let shlex drop the rest
    try:
        tokens = list(lexer)
    except ValueError:
        return "could not parse the command"
    commands, current, i = [], [], 0
    while i < len(tokens):
        token = tokens[i]
        if token in SEPARATORS:
            if not current:
                return "empty command segment"
            commands.append(current)
            current = []
        elif token in (">", ">>", "&>", ">&", ">|"):
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if current and current[-1] in ("1", "2"):
                current.pop()  # file-descriptor prefix, e.g. 2>/dev/null
            if not (target == "/dev/null" or (token == ">&" and target in ("1", "2"))):
                return "output redirection is only allowed to /dev/null"
            i += 1
        elif token == "<":
            i += 1  # reading a file is fine
        elif set(token) <= set("&()<>|;"):
            # shlex splits unquoted operators into punctuation-only tokens; quoted text (e.g. 'a|b') stays whole.
            return f"`{token}` is not allowed"
        else:
            current.append(token)
        i += 1
    if current:
        commands.append(current)
    if not commands:
        return "empty command"
    for argv in commands:
        reason = check_command(argv)
        if reason:
            return reason
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("agent_type") not in REVIEWER_AGENTS:
        return 0
    tool, tool_input = data.get("tool_name"), data.get("tool_input") or {}
    if tool in ("Read", "Grep", "Glob"):
        return 0
    if tool == "Bash":
        reason = check_bash(tool_input.get("command") or "")
        result = (decision("allow", "tf-review: read-only command") if reason is None else
                  decision("deny", f"tf-review reviewers are read-only: {reason}. "
                                   "Use Read, or a plain git log/show/blame/diff, rg or grep command."))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        result = (decision("allow", "tf-review: review.md") if REVIEW_FILE_RE.search(path) else
                  decision("deny", "tf-review reviewers may only write review.md in their job directory."))
    else:
        # Web access, MCP tools, nested agents and skills would escape the confinement above.
        result = decision("deny", f"tf-review reviewers cannot use {tool}.")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
