# Teamfluencer-Dev / .github

Org defaults: shared reusable workflows for Teamfluencer-Dev repos.

## Reusable workflows

### `claude-review.yml` — Senior-dev PR review by Claude

Auto-reviews every PR opened/updated in caller repos, posts a single
structured comment (verdict + findings + what looks good).

**Caller usage:**

```yaml
# .github/workflows/pr-review.yml in a caller repo
name: PR Review
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  claude:
    uses: Teamfluencer-Dev/.github/.github/workflows/claude-review.yml@main
    secrets: inherit
```

**Override model per-repo (e.g., use Sonnet for a cheaper repo):**

```yaml
jobs:
  claude:
    uses: Teamfluencer-Dev/.github/.github/workflows/claude-review.yml@main
    with:
      model: claude-sonnet-4-6
    secrets: inherit
```

**Skip a single PR:** add the `skip-review` label.

## Prerequisites

- The [`claude` GitHub App](https://github.com/apps/claude) must be
  installed on each caller repo.
- Org-level secret `ANTHROPIC_API_KEY` must exist and be scoped to caller
  repos.
