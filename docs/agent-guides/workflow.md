# Workflow Guide

## Working Repo

- Use `C:\gitclone\double-pendulum-playground` for final edits.
- Treat `C:\gitclone\private` as scratch only unless the user explicitly wants work there.
- Before editing, confirm:

```powershell
git status
git branch --show-current
```

## Branch And Push Flow

- Preferred sequence:

```powershell
git checkout -b feature/<topic>
git add <files>
git commit -m "<message>"
git push -u origin feature/<topic>
```

- If a push is rejected because earlier history contained a large file, flatten the branch before pushing again:

```powershell
git reset --soft origin/main
git add -A
git commit -m "<new single commit>"
git push -u origin <branch>
```

## Pre-Push Checks

- Keep only intentional sample assets.
- Check tracked file sizes before push:

```powershell
Get-ChildItem -File -Recurse .\docs |
  Sort-Object Length -Descending |
  Select-Object -First 10 Name,@{Name='MB';Expression={[math]::Round($_.Length/1MB,2)}}
```

- Verify the exact diff:

```powershell
git status --short
git diff --stat
```
