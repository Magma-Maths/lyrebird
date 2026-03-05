# Installation

This guide walks through setting up Lyrebird for a pair of public and private repositories.

## 1. Create a GitHub App

1. Go to your organization's settings: **Settings > Developer settings > GitHub Apps > New GitHub App**
2. Give it a name (e.g. `lyrebird-agent`)
3. Set the homepage URL to anything (e.g. your org's GitHub page)
4. Uncheck **Active** under Webhook (Lyrebird uses Actions, not webhooks)
5. Set these permissions:
   - **Repository permissions:**
     - **Actions:** Read and write
     - **Issues:** Read and write
     - **Metadata:** Read-only (selected automatically)
6. Click **Create GitHub App**
7. Note the **App ID** from the app's settings page
8. Under **Private keys**, click **Generate a private key** and save the `.pem` file

## 2. Install the App on your repos

1. From the App's settings page, click **Install App**
2. Choose your organization
3. Select **Only select repositories** and add both your public and private repos
4. Click **Install**

## 3. Deploy with the script

The easiest way to deploy is with the included script:

```bash
# Copy and fill in the config
cp scripts/.env.example scripts/.env
```

Edit `scripts/.env`:

```bash
ORG="yourorg"
PUBLIC_REPO_NAME="your-public-repo"
PRIVATE_REPO_NAME="your-private-repo"
LYREBIRD_REPO="yourorg/lyrebird"        # where this repo lives
APP_ID="123456"                          # from step 1
BOT_LOGIN="lyrebird-agent[bot]"          # your app name + [bot]
PEM_FILE="/path/to/your-app.pem"         # from step 1
```

Then run:

```bash
# Deploy via PRs (recommended for production)
./scripts/deploy.sh

# Or push directly to main
./scripts/deploy.sh --no-pr
```

The script will:
- Set repository variables and secrets on both repos
- Copy the workflow files into each repo

## 4. Manual deployment

If you prefer to set things up by hand:

### Workflow files

Copy these workflow files into `.github/workflows/` in the respective repos:

**Public repo:**
- `workflows/public-dispatch.yml`

**Private repo:**
- `workflows/handle-public-event.yml`
- `workflows/handle-private-issue.yml`
- `workflows/handle-private-comment.yml`

### Repository variables

Set these on **both** repos (Settings > Secrets and variables > Actions > Variables):

| Variable | Value |
|----------|-------|
| `LYREBIRD_APP_ID` | Your GitHub App ID |
| `LYREBIRD_REPO` | `yourorg/lyrebird` |
| `PUBLIC_REPO` | `yourorg/your-public-repo` |
| `PUBLIC_REPO_NAME` | `your-public-repo` |
| `PRIVATE_REPO` | `yourorg/your-private-repo` |
| `PRIVATE_REPO_NAME` | `your-private-repo` |
| `BOT_LOGIN` | `your-app-name[bot]` |

### Repository secret

Set on **both** repos (Settings > Secrets and variables > Actions > Secrets):

| Secret | Value |
|--------|-------|
| `LYREBIRD_APP_PRIVATE_KEY` | Contents of the `.pem` file |

## 5. Verify

Open a test issue on the public repo. Within a minute you should see:

1. A workflow run on the public repo (dispatching the event)
2. A workflow run on the private repo (handling the event)
3. A new issue on the private repo titled `[public #N] <your issue title>`
4. A mapping comment on the public issue linking to the private one

## Optional configuration

These environment variables can be set in the workflow files to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `RESOLUTION_LABELS` | *(see README)* | JSON mapping of resolution keys to labels/notes |
| `MAPPING_COMMENT_TEMPLATE` | `Thanks for the report! Our team is tracking this and will post updates here.` | Template for the public mapping comment |
| `NEEDS_RESOLUTION_LABEL` | `needs-public-resolution` | Label applied when private is closed without a resolution |
