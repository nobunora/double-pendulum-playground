# AGENTS.md

This file is the index for repository-specific operating notes.

Start here, then open the focused guide that matches the task.

## Index

- Workflow basics:
  - `docs/agent-guides/workflow.md`
- Qiita publishing and article sync:
  - `docs/agent-guides/qiita.md`
- Known failure modes and patterns to avoid:
  - `docs/agent-guides/ng-patterns.md`

## Current High-Signal Reminders

- Use `C:\gitclone\double-pendulum-playground` as the real working repo.
- Treat GitHub as the source of truth for the Qiita article in `public/`.
- The main Qiita article file is:
  - `public/double_pendulum_chaos_map_playground.md`
- If an article is deleted on Qiita, remove its corresponding `.md` from `public/` too.
- Large MP4s should not rely on GitHub `blob` preview alone; use thumbnails and lightweight previews.
