# /paylas — PR list mode (`tur: pr-listesi`)

Read this only when the user hands over PRs (numbers like `api#1976`, PR links,
"PR'larımı paylaş", "PR'larım", "merge sırası"). The table is built from GitHub instead of
from memory, written to one file and shared with the single `hizli` command of SKILL.md
step 4. No question, no card. `TFB` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tf_bilgi.py"`
(always type the full form).

## PR list mode

When the user hands over PRs (numbers like `api#1976`, PR links, "PR'larım",
"merge sırası"), build the table from GitHub instead of from memory:

- Refs given → run `TFB prler <ref...>` directly (read-only; needs `gh`, so not on the
  köprü path without GitHub: then write the table from what the user gave and say so).
  "Benim PR'larım" → `TFB prler @me [--repo <repo>]...`. No refs → fetch `@me`. Repo
  aliases: `api`, `web`, `admin`, `app`, `landing`, or full repo names.
- Rows: `pr`, `baslik`, `url`, `dal`, `taban`, `claude_review`
  (`basarili | bekliyor | basarisiz | yok`), `merge_durumu_tr`, `bagimli` (the PR
  this one is stacked on). Report `hatalar` as one line under the table.
- Table (body), one row per PR in merge order (stack parents first, then the
  order the user gave):

  `| # | PR | Başlık | Bağımlılık | claude-review | Merge sırası | Merge türü | Deploy kontrolü | Kaçınılacak saat |`

  `PR` = `[api#1976](url)`; `claude-review`: basarili → "yeşil", bekliyor →
  "bekliyor", basarisiz → "kırmızı", yok → "yok — /pr-review gerekli";
  `Merge türü` = "merge commit" for stacked PRs (squash breaks the stack), else
  what the user says or "—"; `Deploy kontrolü` and `Kaçınılacak saat` from the
  user's text or the repo rules they cite, else "—". Then "Nasıl doğrulanır" and
  "Bilinen tuzaklar", one short list each, from the user's words (else "—").
- Never run a gh command that writes. Never run `/pr-review` from here.

## Share it

1. Write the file with the Write tool to `~/.tf-bilgi/gecici/pr-listesi-<YYYYMMDD-HHMMSS>.md`
   (absolute path: the home folder + `/.tf-bilgi/gecici/…`): first line `# PR listesi`,
   then the table, the `hatalar` line if any, "Nasıl doğrulanır" and "Bilinen tuzaklar".
2. Run the single `hizli` command of SKILL.md step 4 with `--ek <that file>` and the
   user's own words in the heredoc (same `--yonetim` / `--haber simdi` rules). The helper
   deletes the file under `gecici/` after it is sent.
3. Reply as in SKILL.md step 5: the `satir` line (plus one short line when `hatalar` was
   not empty).
