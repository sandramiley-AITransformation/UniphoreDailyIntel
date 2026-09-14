# Uniphore Daily Intel — Publishing Kit

Automated daily publishing pipeline for the **Daily Intel** competitive‑intelligence
brief. It takes an authored HTML edition, archives it, builds a browsable
"Past Editions" index, and publishes a styled page to a public URL — on a schedule,
with no human in the loop.

This kit is standard‑library Python 3 + Bash + git. No frameworks, no build step.

---

## 1. What it does

Two moving parts:

1. **Content source (already exists as a Claude routine):** a scheduled Claude agent
   researches the day's news and writes the edition into a **Claude artifact** (a
   single self‑contained HTML page: masthead, sticky anchor nav, category cards,
   "angle" callouts, sources footer).
2. **This kit (the "mirror + publish" pipeline):** a second scheduled agent pulls the
   latest artifact, converts it to a clean standalone `index.html`, archives it, and
   publishes it to a public site with a permanent URL and an archive of every past
   edition.

```
  ┌─────────────────────┐        ┌──────────────────────────────────────────┐
  │ Claude routine (AM)  │ writes │ Claude Artifact  (the authored edition)   │
  │  researches + drafts │───────▶│  https://claude.ai/code/artifact/<id>     │
  └─────────────────────┘        └──────────────────────────────────────────┘
                                                │  (read)
                                                ▼
  ┌───────────────────────────────────────────────────────────────────────┐
  │ THIS KIT — runs on a schedule in Claude Enterprise                      │
  │                                                                         │
  │  import_artifact.py   artifact export ─▶ clean standalone index.html    │
  │  generate_report.py   index.html ─▶ Markdown + HTML archive,            │
  │                       canonical permalink, per-edition pages, archive   │
  │  launch.sh            commits source repo, publishes public/ to Pages   │
  └───────────────────────────────────────────────────────────────────────┘
                                                │  (git push)
                                                ▼
  ┌───────────────────────────────────────────────────────────────────────┐
  │ PUBLIC SITE (GitHub Pages or any static host)                          │
  │   /                      → latest edition (permalink)                   │
  │   /archive.html          → "Past Editions" index                       │
  │   /editions/YYYY-MM-DD.html → every past edition                       │
  └───────────────────────────────────────────────────────────────────────┘
```

> **Note on the content source:** this kit publishes whatever the artifact contains —
> it does **not** itself research or write the news. If you'd rather have the publish
> agent do its own research and write `index.html` directly (skipping the artifact),
> see "Alternative: single-agent" at the end.

---

## 2. Files in this kit

| File | Purpose |
|---|---|
| `config.py` | **The only file you edit.** Site URL, public repo, artifact id. |
| `import_artifact.py` | Converts a Claude artifact export into a clean `index.html`. |
| `generate_report.py` | Builds the Markdown/HTML archives, canonical permalink, per‑edition pages, and the archive index; injects the "Past Editions" nav link. |
| `launch.sh` | Orchestrator: generate → commit/push source → publish public site. |
| `examples/sample-edition.html` | A real edition, so you can see the expected HTML structure. |

Generated at runtime (not shipped): `daily-reports/`, `reports/`, `public/`.

---

## 3. Prerequisites

- **git** and **Python 3.8+** on whatever host runs the pipeline.
- A **git host** for two repositories (GitHub, or adapt for internal GitLab — see §7):
  - a **source** repo (holds the scripts, `index.html`, and the archive), and
  - a **public** repo whose root is served as the website.
- A **static hosting** target for the public repo (GitHub Pages, or internal — see §7).
- **Claude Enterprise** with Claude Code **routines** (scheduled cloud agents) enabled.
- The **Claude GitHub App** installed on your org with **write** access to both repos
  (this is the step that lets the scheduled cloud agent push — see §6.1).

---

## 4. Configure (`config.py`)

Edit the four values:

```python
PUBLIC_SITE   = "https://<org>.github.io/<public-repo>"        # site root, no trailing slash
PUBLIC_REMOTE = "https://github.com/<org>/<public-repo>.git"   # public repo git URL
ARTIFACT_URL  = "https://claude.ai/code/artifact/<artifact-id>"
ARTIFACT_ID   = "<leading-segment-of-artifact-id>"             # e.g. "665af250"
```

`ARTIFACT_ID` is the first dash‑separated segment of the artifact id in the URL.

---

## 5. One-time deployment (hosting)

1. **Create the two repos** under your org, e.g. `daily-intel` (source) and
   `daily-intel-public` (public). Push this kit into the **source** repo.
2. **Seed an edition.** Put a valid edition at the source repo root as `index.html`
   (use `examples/sample-edition.html` as the shape to match, or let the mirror step
   produce it — see §6).
3. **Fill in `config.py`** and commit it.
4. **Enable GitHub Pages** on the **public** repo: Settings → Pages → Deploy from a
   branch → `main` / `/ (root)`. (Public repos get Pages on the free tier; private
   repos need GitHub Pro/Team/Enterprise. See §7 for internal hosting instead.)
5. **First publish, manually, from a workstation** (validates everything before you
   automate):
   ```bash
   ./launch.sh --no-open
   ```
   You should see it commit the source repo and print
   `published → https://<org>.github.io/<public-repo>/`.
6. **Verify:** open `PUBLIC_SITE` (renders the edition) and `PUBLIC_SITE/archive.html`
   (lists editions). Pages takes ~30–90s to rebuild after each push.

---

## 6. Automate on Claude Enterprise

### 6.1 Install the Claude GitHub App (required for the agent to push)

The scheduled cloud agent runs in a sandbox. Cloning a **public** repo needs no auth,
but **pushing needs the Claude GitHub App installed with write access**. Install it for
your org and grant **both** repos:

- https://github.com/apps/claude/installations/select_target → select the org →
  add both repos (or "All repositories") → Install.

> If you skip this, the agent clones and generates fine but the push fails with
> `403 … Claude doesn't have GitHub access to <repo>`. This is the #1 setup gotcha.
> With the App installed, the repos may stay **private** — the App grants read+write
> regardless of visibility.

### 6.2 Create the scheduled routine

Create a routine (scheduled cloud agent) using the prompt and settings in
**`ROUTINE.md`**. Summary:

- **Schedule:** daily, shortly after the content routine finishes (e.g. `0 14 * * *`
  UTC = 07:00 America/Los_Angeles). Cron is UTC — mind DST (see §8).
- **Model:** `claude-sonnet-5` is sufficient (the publish agent doesn't research).
- **Repos / sources:** attach **both** the source and public repos.
- **Tools:** `Bash, Read, Write, Edit, Glob, Grep, Artifact`.
- **Prompt:** paste from `ROUTINE.md` (edit the artifact URL and repo path).

### 6.3 Test it

Trigger the routine manually once and read the run log. A healthy run ends with
`published → …` and both git pushes succeeding. Then the daily schedule is live.

---

## 7. Adapting the publish step (internal cloud / non-GitHub hosting)

`launch.sh` publishes by cloning `PUBLIC_REMOTE`, copying the generated `public/`
tree into it, committing, and pushing — GitHub Pages then serves it. To publish to
**internal** hosting instead, replace **step 3** in `launch.sh` (the block under
"Publishing public page…") with your own deploy, keeping the `public/` directory as
the source of truth. Common swaps:

- **Internal GitLab Pages / Bitbucket:** change `PUBLIC_REMOTE` to that repo's URL;
  enable that platform's Pages equivalent. No script change needed.
- **Object storage / static host (S3, Azure Blob, internal CDN):** replace the clone
  /commit/push with your upload command, e.g. `aws s3 sync public/ s3://<bucket>/`.
- **Internal web server:** `rsync -a --delete public/ user@host:/var/www/daily-intel/`.

Everything upstream of the publish (`import_artifact.py`, `generate_report.py`, the
`public/` layout) is host‑agnostic.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `403 … Claude doesn't have GitHub access` on push | Claude GitHub App not installed with **write** for the repo/org. See §6.1. |
| Run stalls on a "sensitive file" permission prompt | A shell command touched a `.claude/` path. The kit avoids this — `import_artifact.py` auto‑discovers the export; never `cat`/`cp` a `.claude` path in the prompt. |
| `import_artifact: no artifact export found` | The `Artifact read` step didn't run first, or `ARTIFACT_ID` is wrong. |
| Publish shows "No changes to push" | Content identical to last run. The heartbeat (`public/last-updated.txt`) normally forces a push each run so real failures surface as errors. |
| Page shows source, not rendered, on GitHub | You're viewing the repo `blob`/`raw` URL. Use the **Pages** URL (`PUBLIC_SITE`). `raw.githubusercontent.com` serves `text/plain` and won't render. |
| Fires at the wrong hour twice a year | Cron is fixed UTC; it doesn't follow DST. Adjust the hour after clocks change. |
| Rate‑limited mid‑run | Account hit a usage cap; re‑run after it resets. |

---

## 9. Security & privacy notes

- The published page and the public repo are **world‑readable and indexable**. Keep
  anything sensitive out of the edition content and the source repo, or host the
  public site behind your internal access controls (§7).
- The scripts contain **no secrets**. Auth is handled entirely by the Claude GitHub
  App (in the cloud) or your workstation's git credentials (manual runs).
- The pipeline never emails, posts, or sends anything outward beyond the git push to
  the repos you configure.

---

## Alternative: single-agent (no separate artifact)

If you don't want the two‑routine split, one routine can do it all: research the news,
write `index.html` directly in the source repo (matching `examples/sample-edition.html`),
then run `./launch.sh --no-open`. In that case you don't need `import_artifact.py` or the
`Artifact` tool — just give the routine web‑search tools and a prompt describing the
sections. The publish half of the kit is identical.
