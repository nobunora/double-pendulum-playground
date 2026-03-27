# AGENTS.md

This repository-specific guide captures the workflow that worked well for the
double pendulum project so the next run can succeed in one pass.

## Work In The Real Git Repo

- Use `C:\gitclone\double-pendulum-playground` as the working repository.
- Do not make final project edits in `C:\gitclone\private` and then copy them later unless explicitly requested.
- Before editing or committing, confirm:

```powershell
git status
git branch --show-current
```

- Keep changes on a feature branch, then push and open a PR.

## Commit And Push Flow

- Preferred branch flow:

```powershell
git checkout -b feature/<topic>
git add <files>
git commit -m "<message>"
git push -u origin feature/<topic>
```

- If GitHub rejects a push because a large file existed in an earlier commit,
  rewrite the local branch history before pushing again. The working pattern is:

```powershell
git reset --soft origin/main
git add -A
git commit -m "<new single commit>"
git push -u origin <branch>
```

## Generated Asset Policy

- Do not commit every generated PNG/MP4 by default.
- Keep only representative samples in the repo.
- Prefer a few hand-picked files in `docs/` and `docs/images/`.
- GitHub will reject files larger than 100 MB. Check before push:

```powershell
Get-ChildItem -File -Recurse .\docs | Sort-Object Length -Descending | Select-Object -First 10 Name,@{Name='MB';Expression={[math]::Round($_.Length/1MB,2)}}
```

- If sample assets are reduced after an initial commit, make sure those deletions
  are committed too before pushing.

## Qiita Publishing Workflow

- Keep Qiita article drafts in `public/`.
- Current Qiita draft file:
  - `public/double_pendulum_chaos_map_playground.md`
- Current Qiita config files:
  - `qiita.config.json`
  - `package.json`
  - `.github/workflows/publish_qiita.yml`

- The GitHub Actions workflow assumes the repository secret is named:
  - `QIITA_TOKEN`

- Do not hardcode tokens into files, commits, scripts, or markdown.
- Keep credentials out of version control. `.gitignore` should continue to ignore:
  - `node_modules/`
  - `credentials.json`

## Qiita Workflow Behavior

- The workflow publishes on:
  - push to `main`
  - push to `master`
  - manual `workflow_dispatch`

- The article currently references image/video assets using `main` branch URLs.
  This means:
  - preview on the feature branch may not fully reflect final assets
  - after merge to `main`, links become stable

- If local Node.js is unavailable, that is acceptable. The repo is set up so
  GitHub Actions can run Qiita CLI on the runner.

## Practical Lessons From This Run

- If `apply_patch` is used while another repo is the real target, use absolute
  paths or verify the target repo before patching.
- When creating article/workflow files, verify they landed in the intended repo:

```powershell
git status --short
```

- If a file unexpectedly appears in another workspace, copy it into the real repo
  immediately and re-check status.

## Final Pre-Push Checklist

- Code files are in the correct repo.
- Only intended sample assets are tracked.
- No tracked file exceeds 100 MB.
- `git status` is clean after commit.
- Feature branch is pushed.
- PR URL is ready.
