# NG Patterns

## Qiita / GitHub Actions

- Do not rerun an old failed workflow and assume it uses the latest YAML.
  - A rerun can still execute the old workflow definition from that run's commit.
- Do not enable `cache: "npm"` in `actions/setup-node` unless the repo actually contains a supported lockfile such as `package-lock.json`.
- Do not leave deleted Qiita articles as `.md` files under `public/`.
  - This was a real failure cause in this repo.
- Do not set `id: null` in an article that should update an existing Qiita post.
  - That causes duplicate new posts.

## Article Assets

- Do not link large MP4 samples only through the GitHub `blob` page when the goal is preview from the article.
  - GitHub can refuse to preview large files.
- Prefer:
  - thumbnail image
  - lightweight preview MP4
  - full raw MP4 link
  - GitHub source link

## Repo Hygiene

- Do not assume Qiita CLI will clean old synced article files for you.
- Do not hardcode tokens in source, scripts, markdown, or commit messages.
- Do not commit every generated PNG or MP4 by default.
