# Lyrebird

Public-to-private GitHub issue mirroring. Lyrebird automatically copies public issues and comments into a private repository so engineers can work in one place, while providing selective, curated updates back to the public issue.

## How it works

Lyrebird runs as a set of GitHub Actions workflows. A thin workflow on the public repo forwards issue and comment events to the private repo via `repository_dispatch`. Handler workflows on the private repo check out Lyrebird, install it, and run the appropriate handler.

All mapping state lives in GitHub itself (HTML comment markers in issue bodies and comments) — no external database or key-value store.

### Public to private (automatic)

- **Issue opened** — creates a private mirror with title `[public #N] <title>`, body with metadata and delimiters, and a mapping comment on the public issue linking to the private one.
- **Issue edited** — updates private title and body (only the public section between delimiters).
- **Comment created/edited/deleted** — mirrors to private, with edits updating in-place and deletes replaced by a tombstone.
- **Labels added/removed** — mirrored 1:1 into private, auto-creating labels as needed.
- **Issue closed/reopened** — adds/removes `public:closed` and `public:closed-by-reporter` labels on the private issue, plus an audit comment. Does not change private open/closed state.

### Private to public (selective)

- **`/public <message>`** — posts `<message>` as a comment on the mapped public issue.
- **`/public-close <resolution> [note]`** — normalizes resolution labels, closes both private and public issues, and posts the note (or a default message) on the public issue.
- **Private issue closed** — if exactly one resolution label is present, closes the public issue with a default note. Otherwise, applies `needs-public-resolution` and nudges.
- **Private issue reopened** — removes resolution and `needs-public-resolution` labels.
- **Private label changes** — mirrored to public only if that label already exists on the public repo (the public label set acts as an implicit allowlist).

## Prerequisites

- Python >= 3.10
- A [GitHub App](https://docs.github.com/en/apps) with **Issues: read/write** and **Metadata: read** permissions, installed on both repos.

## Setup

### 1. Install workflows

**Public repo** — copy `workflows/public-dispatch.yml` to `.github/workflows/`.

**Private repo** — copy these to `.github/workflows/`:
- `workflows/handle-public-event.yml`
- `workflows/handle-private-issue.yml`
- `workflows/handle-private-comment.yml`

### 2. Configure variables and secrets

Set these as repository variables and secrets (or at the organization level):

| Name | Type | Description |
|------|------|-------------|
| `LYREBIRD_APP_ID` | Variable | GitHub App ID |
| `LYREBIRD_APP_PRIVATE_KEY` | Secret | GitHub App private key (PEM) |
| `LYREBIRD_REPO` | Variable | This repo, e.g. `yourorg/lyrebird` |
| `PUBLIC_REPO` | Variable | Full name of public repo, e.g. `yourorg/public-repo` |
| `PUBLIC_REPO_NAME` | Variable | Short name, e.g. `public-repo` |
| `PRIVATE_REPO` | Variable | Full name of private repo |
| `PRIVATE_REPO_NAME` | Variable | Short name of private repo |
| `BOT_LOGIN` | Variable | GitHub App bot login, e.g. `lyrebird[bot]` |

### 3. Optional configuration

These environment variables can be set in the workflow files to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `RESOLUTION_LABELS` | *(see below)* | JSON mapping of resolution keys to labels/notes |
| `MAPPING_COMMENT_TEMPLATE` | `Internal tracking: {private_repo}#{private_issue_number}` | Template for the public mapping comment |
| `CLOSED_LABEL` | `public:closed` | Label applied to private issue when public is closed |
| `CLOSED_BY_REPORTER_LABEL` | `public:closed-by-reporter` | Label applied when original reporter closes |
| `NEEDS_RESOLUTION_LABEL` | `needs-public-resolution` | Label applied when private is closed without a resolution |

#### Default resolution labels

| Key | Label | Default public note | State reason |
|-----|-------|-------------------|--------------|
| `fixed` | `external:fixed` | Fixed on main. Thanks for the report. If you still see this after updating, please comment here with details. | `completed` |
| `wontfix` | `external:wontfix` | Closing as not planned at this time. Thanks for taking the time to report it. | `not_planned` |
| `duplicate` | `external:duplicate` | Closing as a duplicate. Please follow the linked issue for updates. | `completed` |
| `cannot-reproduce` | `external:cannot-reproduce` | We could not reproduce this with the information available. If you can share steps/logs, we can reopen. | `completed` |

To customize, set `RESOLUTION_LABELS` as JSON:

```json
{
  "fixed": {"label": "external:fixed", "note": "Custom note here.", "state_reason": "completed"},
  "wontfix": {"label": "external:wontfix", "note": "Custom note.", "state_reason": "not_planned"}
}
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Contributing

This project follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Commit messages must be structured as:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`.

## Design

See [plan.md](plan.md) for the full specification, including architecture decisions, mapping/idempotency strategy, failure handling, and rollout plan.

### Key design properties

- **No external state** — all mapping lives in GitHub issue comments and bodies via HTML comment markers.
- **Idempotent** — never creates duplicate private issues. A 3-step lookup (mapping comment, fallback body search, create) with self-healing ensures recovery from partial failures.
- **Loop-safe** — all events from the bot's own identity are ignored.
- **Concurrency-safe** — GitHub Actions concurrency groups keyed by issue `node_id` serialize events per issue.

## License

TBD
