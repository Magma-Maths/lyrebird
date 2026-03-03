# Lyrebird Workflow Setup

## Prerequisites

1. A GitHub App with **Issues: read/write** and **Metadata: read** permissions, installed on both the public and private repos.
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

Copy `public-dispatch.yml` to `.github/workflows/public-dispatch.yml`.

### Private repo

Copy all three files to `.github/workflows/`:
- `handle-public-event.yml`
- `handle-private-issue.yml`
- `handle-private-comment.yml`

## How it works

1. An issue or comment event fires on the public repo.
2. `public-dispatch.yml` forwards the event to the private repo via `repository_dispatch`.
3. `handle-public-event.yml` picks up the dispatch, installs lyrebird, and runs the appropriate handler.
4. For private-side events (close, reopen, label changes, slash commands), `handle-private-issue.yml` and `handle-private-comment.yml` run directly.

## Concurrency

All workflows use GitHub Actions concurrency groups keyed by issue `node_id` with `cancel-in-progress: false`. This serializes events per issue and prevents race conditions.
