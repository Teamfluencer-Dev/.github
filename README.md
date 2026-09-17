# Teamfluencer-Dev / .github

Org defaults for Teamfluencer-Dev repositories.

## Mandatory Claude PR review (`tf-review` plugin)

Every repository's default branch has a ruleset named **Claude review zorunlu**:

- changes land only through pull requests (no direct pushes), and
- the PR head commit must carry a successful **`claude-review`** commit status.

That status is set by the `tf-review` Claude Code plugin. The review runs in the
developer's own Claude Code session, on their Claude subscription — never on
Anthropic API credits — by a fresh-context Opus agent.

### One-time setup (each developer)

```bash
claude plugin marketplace add Teamfluencer-Dev/.github
claude plugin install tf-review@teamfluencer
```

Also required: the GitHub CLI logged in (`gh auth login`), Claude Code logged in
with a Claude subscription (`/login`), and no `ANTHROPIC_API_KEY` in the
environment Claude Code starts from (the plugin refuses to run otherwise).

### Usage

Open Claude Code in the repository and run:

```
/pr-review            # the PR of the current branch
/pr-review 123        # a PR number or URL
/pr-review 123 --full # force a full review
```

What happens:

1. `scripts/tf_review.py prepare` resolves the PR and picks a mode:
   - **full** — first review of the PR (or `--full`, or more than 1,500 changed
     lines since the last review, or the last reviewed commit was force-pushed
     away);
   - **incremental** — code changed since the last review; only the delta is
     reviewed and earlier findings are tracked;
   - **carry** — nothing in the PR's files changed since the last review (e.g. a
     base-branch merge) or only docs changed: the status is re-issued without an
     agent run;
   - **docs-only** — the PR only touches `*.md`, `*.mdx`, `*.rst`, `docs/` or
     `LICENSE`.
2. For full / incremental reviews, the skill launches `full-reviewer` or
   `incremental-reviewer` (Opus, zero context). The agent reads the job directory
   (`.tf-review/pr-<n>/` in the repo, git-excluded) and the code at the PR head,
   and writes `review.md`.
3. `scripts/tf_review.py post` posts the review as a PR comment, sets
   `claude-review` = success on the reviewed commit, collapses older review
   comments and removes the job directory.

Every new push needs `/pr-review` again before merging; later runs are
incremental or carry-forward, so they are quick.

The verdict (APPROVE / NEEDS-CHANGES / BLOCKER) is informational: the check
requires that a review happened, not that it approved.

### Safeguards and limits

- The reviewer agents read text written by others, so a plugin `PreToolUse` hook
  (`hooks/reviewer_guard.py`) confines them: Bash only for single-line read-only
  commands (git history, `rg`/`grep`, file viewers — auto-approved, so reviews
  run without permission prompts), and writes only to their own `review.md`.
- PR descriptions and earlier reviews are wrapped in per-job random delimiters.
- Pull requests from forks are refused.
- Markdown that instructs Claude or the reviewer (`CLAUDE.md`, `AGENTS.md`,
  `SKILL.md`, `.claude/`, `claude-plugins/`, `.github/claude-review-context.md`)
  is reviewed like code, never skipped as documentation.
- Review state is read only from unedited marker comments written by org
  members or collaborators.
- The gate is a team process control, not a security boundary: anyone with push
  access can technically create a `claude-review` status through the API.

Repo-specific review invariants live in each repository's
`.github/claude-review-context.md` (INV-### / INV-T##) and are handed to the agent.

### Updating the plugin

```bash
claude plugin marketplace update teamfluencer
claude plugin update tf-review@teamfluencer
```

`/pr-review` prints a reminder when a newer version is published. Bump
`claude-plugins/tf-review/.claude-plugin/plugin.json` `version` with every change.

### Tests

```bash
python3 -m unittest discover -s claude-plugins/tf-review/tests -v
```

### Emergency

An org admin can temporarily set the ruleset to *Disabled* in the repository's
Settings → Rules → Rulesets (for example if a hotfix cannot wait for a review).
Re-enable it right after.

## Reusable workflows

### `claude-review.yml` — disabled

The former API-billed CI review. It is now a stub whose only job is always
skipped, so existing `pr-review.yml` callers keep working without spending
runner minutes or API credits. The v11 review instructions moved into the
plugin's agents.
