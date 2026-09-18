# Test coverage policy

Applies to the six product repositories: teamfluencerapi, teamfluencer-web,
teamfluencer-admin-web, teamfluencer-landing, teamfluencerapp and
teamfluencer-trend-analysis. Tracked in Jira epics TA-2223, TF-651 and APP-224.

## Current phase: visibility (no coverage gates)

Every repository's PR CI produces an `lcov.info` report and publishes it with
the shared action below. Nothing fails because of coverage yet; the first
weeks of numbers set the real baseline before any gate is switched on.

```yaml
- uses: Teamfluencer-Dev/.github/actions/coverage-summary@main
  if: always()
  with:
    lcov: coverage/lcov.info
    title: Coverage — <repo>
```

The action writes a totals table and the ten weakest directories to the job
summary and uploads the report as the `coverage-lcov` artifact (14 days). It
never fails the job.

## What counts

Coverage measures source that runs in production. Excluded everywhere:

- type declarations (`*.d.ts`, type-only `types/` folders)
- root-level tool configs (`*.config.*`)
- one-off scripts: `scripts/**` and root-level `backfill-*`, `check-*`,
  `run-*`, `create-*` files
- generated output: `build/`, `dist/`, `documentation/dist/`, minified files
- test support: `fixtures/`, `support/`, `_`-prefixed helpers under `__tests__`
- pure `index.ts` re-exports

Exclusions live in each repository's coverage config, never in scattered code
comments. An `istanbul ignore` / `c8 ignore` / `v8 ignore` comment must carry a
reason, and reviewers ask about every new one.

## Planned gates (not active yet)

| Gate | Rule | Jira |
|---|---|---|
| Patch coverage | Changed lines ≥ 70%, raised to 80% after three months | TA-2228 |
| Ratchet | Total coverage may not drop (1% tolerance) | TA-2229 |
| Critical paths | 100% lines and branches in money, auth, subscription and campaign-state code | TA-2229 |
| E2E smoke | 3-5 critical journeys headless on every PR, ≤ 4 minutes | TF-660 |
| Mobile UI smoke | One Maestro flow on an Android emulator (`ui-smoke-android`) | APP-229 |

A repository-wide 100% target is deliberately not part of the policy: it gets
met by shrinking what is measured, not by testing more (the old
`teamfluencerapi/.nycrc.json` measured 11 files at 100% and never ran in CI).

The patch gate will treat these PRs as passing: rename-only (similarity ≥ 90%),
delete-only (no coverable lines), whitespace/comment-only, `revert:` PRs, lock
files, and PRs labelled `hotfix` (the review gate still applies).

## Rules for required checks

- A required job always runs. Filter by path inside the job (a step that
  reports "nothing to check" and succeeds), never with a job-level `paths:` or
  `if:` — otherwise PRs that skip the job wait forever on "Expected".
- Gated E2E specs never depend on production or another repository's deploy:
  they use mocked APIs. Specs that need live services run nightly.
- Budget: at most 10 minutes of gated checks per PR; anything slower runs
  nightly.
- Full E2E suites, headed Chrome, visual and accessibility suites, iOS builds
  and mutation testing run nightly or on demand, never as PR gates.
