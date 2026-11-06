# Lyrebird Workflow Setup

## Prerequisites

1. A GitHub App with **Actions: read/write**, **Contents: read**, **Issues: read/write**, **Metadata: read**, and **Pull requests: read** permissions, installed on both the public and private repos.
2. The public and private repositories.

## Repository Variables & Secrets

Set these on **both repos** (or as organization-level settings):

| Name | Type | Description | Example |
|------|------|-------------|---------|
| `LYREBIRD_APP_ID` | Variable | GitHub App ID | `123456` |
| `LYREBIRD_APP_PRIVATE_KEY` | Secret | GitHub App private key (PEM) | `-----BEGIN RSA...` |
| `LYREBIRD_REPO` | Variable | Lyrebird source repo (public) | `yourorg/lyrebird` |
| `PUBLIC_REPO` | Variable | Full name of public repo | `yourorg/public-repo` |
| `PUBLIC_REPO_NAME` | Variable | Short name of public repo | `public-repo` |
| `PRIVATE_REPO` | Variable | Full name of private repo | `yourorg/private-repo` |
| `PRIVATE_REPO_NAME` | Variable | Short name of private repo | `private-repo` |
| `BOT_LOGIN` | Variable | GitHub App bot login | `lyrebird[bot]` |

## Installation

### Public repo

Copy `issues-dispatch-public-events-to-private-repo.yml` to `.github/workflows/issues-dispatch-public-events-to-private-repo.yml`.

### Private repo

Copy all four files to `.github/workflows/`:
- `issues-handle-public-event.yml`
- `issues-handle-private-issue-events.yml`
- `issues-handle-private-comment-events.yml`
- `issues-sync-public-issues.yml`

For existing installations, follow the [workflow upgrade instructions](../INSTALL.md#upgrading-renamed-workflows).

## How it works

1. An issue or comment event fires on the public repo.
2. `issues-dispatch-public-events-to-private-repo.yml` forwards the event to the private repo via `repository_dispatch`.
3. `issues-handle-public-event.yml` picks up the dispatch, installs lyrebird, and runs the appropriate handler.
4. For private-side events (close, reopen, label changes, slash commands), `issues-handle-private-issue-events.yml` and `issues-handle-private-comment-events.yml` run directly.
5. `issues-sync-public-issues.yml` runs `lyrebird sync` on a daily schedule, and on demand from the Actions tab, to reconcile whatever the event path dropped: it creates missing private mirrors, assigns their area owners, and adds missing labels to existing mirrors.

## Concurrency

`issues-handle-public-event.yml`, `issues-handle-private-issue-events.yml`, and `issues-handle-private-comment-events.yml` each use a concurrency group keyed by the issue's `node_id`, with `cancel-in-progress: false`. This serializes events for the same issue and prevents race conditions.

`issues-sync-public-issues.yml` uses a single repository-wide group, `lyrebird-sync`, with `cancel-in-progress: true`. Sync is not scoped to one issue, so a newer sync run supersedes any run already in progress instead of queuing behind it.

`issues-dispatch-public-events-to-private-repo.yml` declares no concurrency group; it only forwards events to the private repo and does no work that needs serializing.
