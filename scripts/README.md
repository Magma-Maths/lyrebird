# Lyrebird Scripts

This directory contains utility scripts to help develop, test, and demonstrate Lyrebird.

## Prerequisites
All scripts require the [GitHub CLI (`gh`)](https://cli.github.com/) to be installed and authenticated (`gh auth login`).

## `setup-test-repos.sh`
Creates fresh, disposable public and private repositories to safely test Lyrebird without touching your real code. It automates the entire setup process, including creating the repositories, configuring secrets, and installing the workflow files.

**Usage:**
```bash
./scripts/setup-test-repos.sh
```

## `demo.sh`
An automated, non-interactive script that generates a "living demo" in your test repositories. 

Instead of cramming every feature into a single confusing thread, it creates **five distinct scenario issues**:
1. Bug report lifecycle (mirroring, edits, labels, type sync)
2. Edits and deletions (comment edit, comment deletion → tombstone)
3. Slash commands (`/anon`)
4. Close/reopen lifecycle (bidirectional state sync)
5. Resolution enforcement (maintainer nudge → proper label + close)

It also acts as a "narrator", posting explanatory comments in the private issues *before* each action happens so your collaborators can easily follow along with the timeline.

**Usage:**
```bash
./scripts/demo.sh
# or, specify repos directly:
./scripts/demo.sh your-org/public-repo your-org/private-repo
```

## `deploy.sh`
Deploys Lyrebird workflows and configuration to your repositories based on an environment file.

**Usage:**
```bash
./scripts/deploy.sh
```

## `sync-labels.sh`
Synchronizes the custom Lyrebird resolution labels (e.g., `external:completed`, `external:not-planned`) into your private repository.

**Usage:**
```bash
./scripts/sync-labels.sh
```

## Environment Files
You can configure the scripts using environment files (e.g., `env.test`, `env.real`). The scripts will look for configuration variables like `$PUBLIC_REPO` and `$PRIVATE_REPO` to know where to operate.
