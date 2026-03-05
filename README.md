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

Posts `<message>` as a comment on the public issue and acknowledges in private with a link. By default, Lyrebird will attribute the message to you (e.g. `**@your-username**: <message>`). If you wish to post completely anonymously, use the `--anon` flag:
`/public --anon <message>`

### `/public-close <resolution> [note]`

Closes both the private and public issues. `<resolution>` must be one of the configured [resolution labels](#resolution-labels). If `[note]` is given, it is posted on the public issue; otherwise the default note for that resolution is used. Like `/public`, a custom note will be attributed to you unless you use the `--anon` flag before your note:
`/public-close fixed --anon We shipped a fix in v2.1, thanks for the report!`

*(Note: If no custom note is provided, the generic default message is used and is never attributed).*

Example:
```
/public-close completed We shipped a fix in v2.1, thanks for the report!
```

## Closing behavior

When a private issue is closed:
- With **exactly one** resolution label &rarr; the public issue is closed with the corresponding default note.
- With **zero or multiple** resolution labels &rarr; a `needs-public-resolution` label is applied and a comment explains what to do.

When a private issue is reopened, resolution and `needs-public-resolution` labels are removed.

## Resolution labels

Resolution labels control `/public-close` and the automatic close behavior. Each has four parts:

- **key** &mdash; the argument to `/public-close` (e.g. `completed`, `not-planned`)
- **label** &mdash; the private-repo label applied (e.g. `external:completed`)
- **note** &mdash; the default message posted on the public issue
- **state_reason** &mdash; the GitHub close reason (`completed` or `not_planned`)

Defaults:

| Key | Label | Default public note | State reason |
|-----|-------|---------------------|--------------|
| `completed` | `external:completed` | This has been fixed and will be available in the next update. Thanks for the report. If you still see this after updating, please comment here with details. | `completed` |
| `not-planned` | `external:not-planned` | Closing as not planned at this time. Thanks for taking the time to report it. | `not_planned` |
| `cannot-reproduce` | `external:cannot-reproduce` | We could not reproduce this with the information available. If you can share steps/logs, we can reopen. | `not_planned` |

These are set explicitly in the workflow templates (`RESOLUTION_LABELS` in the `env:` block of each `handle-*.yml`). To customize, edit them there or set `RESOLUTION_LABELS` as JSON:

```json
{
  "completed":        {"label": "external:completed",        "note": "Custom note.",  "state_reason": "completed"},
  "not-planned":      {"label": "external:not-planned",      "note": "Custom note.",  "state_reason": "not_planned"},
  "cannot-reproduce": {"label": "external:cannot-reproduce", "note": "Custom note.",  "state_reason": "not_planned"}
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
