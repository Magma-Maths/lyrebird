# Lyrebird

Public-to-private GitHub issue mirroring. Lyrebird automatically copies public issues and comments into a private repository, and lets you post selective, curated updates back to the public issue.

## What happens automatically

When someone opens, edits, or comments on a public issue, Lyrebird mirrors everything into a corresponding private issue:

- New public issue &rarr; private issue created as `[public #N] <title>` with a link back
- Public edits &rarr; private title and body updated
- Public comments &rarr; mirrored to private (edits update in-place, deletes become tombstones)
- Public labels &rarr; mirrored to private, auto-creating missing labels
- Public close/reopen &rarr; private issue state synced (closed/reopened) with an audit comment

## Slash commands

From any private mirrored issue, you can post updates to the public issue:

### `/anon <message>`

Posts `<message>` as an anonymous comment on the public issue and acknowledges in private with a link.

## Closing behavior

When a private issue is closed:
- The **public issue is always closed immediately**.
- With **exactly one** resolution label &rarr; the predefined note is posted on the public issue.
- With **zero or multiple** resolution labels &rarr; the public issue is closed with no comment. A 5-minute delayed check then nudges on the private issue with a `resolution:none` label if no resolution was added.

When a private issue is reopened, resolution and `resolution:none` labels are removed, and the public issue is reopened if it was closed.

Using `/anon` on a closed issue automatically adds `resolution:custom` if no other resolution label is present.

## Resolution labels

Resolution labels control the automatic close behavior. Each has four parts:

- **key** &mdash; the resolution identifier (e.g. `completed`, `not-planned`)
- **label** &mdash; the private-repo label applied (e.g. `resolution:completed`)
- **note** &mdash; the default message posted on the public issue
- **state_reason** &mdash; the GitHub close reason (`completed` or `not_planned`)

Defaults:

| Key | Label | Default public note | State reason |
|-----|-------|---------------------|--------------|
| `completed` | `resolution:completed` | This has been fixed and will be available in the next update. Thanks for the report. If you still see this after updating, please comment here with details. | `completed` |
| `not-planned` | `resolution:not-planned` | Closing as not planned at this time. Thanks for taking the time to report it. | `not_planned` |
| `cannot-reproduce` | `resolution:cannot-reproduce` | We could not reproduce this with the information available. If you can share steps/logs, we can reopen. | `not_planned` |
| `custom` | `resolution:custom` | *(none)* | *(none)* |

These are set explicitly in the workflow templates (`RESOLUTION_LABELS` in the `env:` block of each `handle-*.yml`). To customize, edit them there or set `RESOLUTION_LABELS` as JSON:

```json
{
  "completed":        {"label": "resolution:completed",        "note": "Custom note.",  "state_reason": "completed"},
  "not-planned":      {"label": "resolution:not-planned",      "note": "Custom note.",  "state_reason": "not_planned"},
  "cannot-reproduce": {"label": "resolution:cannot-reproduce", "note": "Custom note.",  "state_reason": "not_planned"},
  "custom":           {"label": "resolution:custom",           "note": "",              "state_reason": null}
}
```

## Setup

See [INSTALL.md](INSTALL.md) for full installation instructions.

## Development

```bash
poetry install
poetry run pytest
```

## Contributing

This project follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Commit messages must be structured as:

```
<type>[optional scope]: <description>
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`.

## License

TBD
