# Lyrebird

Public-to-private GitHub issue mirroring. Lyrebird automatically copies public issues and comments into a private repository, and lets you post selective, curated updates back to the public issue.

## What happens automatically

When someone opens, edits, or comments on a public issue, Lyrebird mirrors everything into a corresponding private issue:

- New public issue &rarr; private issue created as `[public #N] <title>` with a link back
- Public edits &rarr; private title and body updated
- Public comments &rarr; mirrored to private (edits update in-place, deletes become tombstones)
- Public labels &rarr; mirrored to private, auto-creating missing labels
- Public close/reopen &rarr; `public:closed` / `public:closed-by-reporter` labels on private, plus an audit comment (private open/closed state is not changed)

## Slash commands

From any private mirrored issue, you can post updates to the public issue:

### `/public <message>`

Posts `<message>` as a comment on the public issue and acknowledges in private with a link.

### `/public-close <resolution> [note]`

Closes both the private and public issues. `<resolution>` must be one of the configured [resolution labels](#resolution-labels). If `[note]` is given, it is posted on the public issue; otherwise the default note for that resolution is used.

Example:
```
/public-close fixed We shipped a fix in v2.1, thanks for the report!
```

## Closing behavior

When a private issue is closed:
- With **exactly one** resolution label &rarr; the public issue is closed with the corresponding default note.
- With **zero or multiple** resolution labels &rarr; a `needs-public-resolution` label is applied and a comment explains what to do.

When a private issue is reopened, resolution and `needs-public-resolution` labels are removed.

## Resolution labels

Resolution labels control `/public-close` and the automatic close behavior. Each has four parts:

- **key** &mdash; the argument to `/public-close` (e.g. `fixed`, `wontfix`)
- **label** &mdash; the private-repo label applied (e.g. `external:fixed`)
- **note** &mdash; the default message posted on the public issue
- **state_reason** &mdash; the GitHub close reason (`completed` or `not_planned`)

Defaults:

| Key | Label | Default public note | State reason |
|-----|-------|---------------------|--------------|
| `fixed` | `external:fixed` | Fixed on main. Thanks for the report. If you still see this after updating, please comment here with details. | `completed` |
| `wontfix` | `external:wontfix` | Closing as not planned at this time. Thanks for taking the time to report it. | `not_planned` |
| `duplicate` | `external:duplicate` | Closing as a duplicate. Please follow the linked issue for updates. | `completed` |
| `cannot-reproduce` | `external:cannot-reproduce` | We could not reproduce this with the information available. If you can share steps/logs, we can reopen. | `completed` |

These are set explicitly in the workflow templates (`RESOLUTION_LABELS` in the `env:` block of each `handle-*.yml`). To customize, edit them there or set `RESOLUTION_LABELS` as JSON:

```json
{
  "fixed":            {"label": "external:fixed",            "note": "Custom note.",  "state_reason": "completed"},
  "wontfix":          {"label": "external:wontfix",          "note": "Custom note.",  "state_reason": "not_planned"},
  "duplicate":        {"label": "external:duplicate",        "note": "Custom note.",  "state_reason": "completed"},
  "cannot-reproduce": {"label": "external:cannot-reproduce", "note": "Custom note.",  "state_reason": "completed"}
}
```

## Setup

### Prerequisites

- A [GitHub App](https://docs.github.com/en/apps) with **Actions: read/write**, **Issues: read/write**, and **Metadata: read** permissions, installed on both repos.
- Python >= 3.10 (used by the GitHub Actions workflows)

### 1. Install workflows

**Public repo** &mdash; copy `workflows/public-dispatch.yml` to `.github/workflows/`.

**Private repo** &mdash; copy these to `.github/workflows/`:
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

These environment variables can be set in the workflow files:

| Variable | Default | Description |
|----------|---------|-------------|
| `RESOLUTION_LABELS` | *(see above)* | JSON mapping of resolution keys to labels/notes |
| `MAPPING_COMMENT_TEMPLATE` | `Internal tracking: {private_repo}#{private_issue_number}` | Template for the public mapping comment |
| `CLOSED_LABEL` | `public:closed` | Label applied to private issue when public is closed |
| `CLOSED_BY_REPORTER_LABEL` | `public:closed-by-reporter` | Label applied when original reporter closes |
| `NEEDS_RESOLUTION_LABEL` | `needs-public-resolution` | Label applied when private is closed without a resolution |

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
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`.

## Design

See [plan.md](plan.md) for the full specification.

## License

TBD
