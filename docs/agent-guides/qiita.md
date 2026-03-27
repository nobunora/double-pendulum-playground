# Qiita Guide

## Source Of Truth

- Manage Qiita drafts in `public/`.
- Current main article file:
  - `public/double_pendulum_chaos_map_playground.md`
- Current article id:
  - `76a3d75ba4fc98dd1402`
- Current workflow file:
  - `.github/workflows/publish_qiita.yml`

## Publish Model

- GitHub Actions publishes from `main`.
- `QIITA_TOKEN` must exist in Actions secrets.
- The workflow intentionally uses:

```bash
npx qiita publish --all --force
```

- Reason:
  - GitHub is treated as the source of truth.
  - `updated_at` drift on Qiita should not block publish.

## Metadata Sync

- The workflow is allowed to commit synchronized metadata back to GitHub.
- Expect `updated_at` in `public/*.md` to change after a successful publish.
- Do not treat that automatic metadata commit as an unexpected repo mutation.

## Safe Update Flow

1. Edit the intended file in `public/`.
2. Keep the correct `id` in front matter if the article should update an existing Qiita post.
3. Push to `main` or run the workflow manually.
4. If the workflow succeeded but the article still looks stale, check whether Qiita updated the article id that is pinned in front matter.

## When Articles Are Deleted On Qiita

- If an article is manually deleted on Qiita, delete its corresponding `.md` file from `public/` too.
- Qiita CLI does not automatically remove deleted articles from the repo.
- Leaving deleted article files in `public/` can make `publish --all` try to update non-existent item ids and fail the workflow.
