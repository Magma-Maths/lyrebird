"""Parse, build, and resolve mapping markers between public and private issues."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from github import Github
from github.Issue import Issue
from github.IssueComment import IssueComment

from lyrebird.config import Config

logger = logging.getLogger(__name__)

# ── Marker patterns ──────────────────────────────────────────────────────────

MAPPING_COMMENT_RE = re.compile(
    r"<!--\s*mapping:\s*"
    r"public_issue_node_id=(\S+)\s+"
    r"private_issue_number=(\d+)\s*-->"
)

PUBLIC_BODY_NODE_ID_RE = re.compile(
    r"<!--\s*public_issue_node_id:\s*(\S+)\s*-->"
)

PUBLIC_BODY_URL_RE = re.compile(
    r"<!--\s*public_issue_url:\s*(\S+)\s*-->"
)

PUBLIC_COMMENT_ID_RE = re.compile(
    r"<!--\s*public_comment_id:\s*(\d+)\s*-->"
)

BEGIN_PUBLIC_BODY = "<!-- BEGIN PUBLIC BODY -->"
END_PUBLIC_BODY = "<!-- END PUBLIC BODY -->"


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class PrivateMapping:
    """Result of resolving a public issue to its private mirror."""
    private_issue: Issue
    private_issue_number: int
    was_self_healed: bool = False


# ── Pure builders / parsers ──────────────────────────────────────────────────

def parse_mapping_comment(body: str) -> tuple[str, int] | None:
    """Extract (public_node_id, private_issue_number) from a mapping comment."""
    m = MAPPING_COMMENT_RE.search(body)
    if m:
        return m.group(1), int(m.group(2))
    return None


def build_mapping_comment(config: Config, public_node_id: str, private_number: int) -> str:
    """Build the full mapping comment text for the public issue."""
    human = config.mapping_comment_template.format(
        private_repo=config.private_repo,
        private_issue_number=private_number,
    )
    marker = (
        f"<!-- mapping: public_issue_node_id={public_node_id} "
        f"private_issue_number={private_number} -->"
    )
    return f"{human}\n\n{marker}"


def build_private_issue_body(config: Config, public_issue: dict) -> str:
    """Build the body for a new private issue mirroring a public one."""
    url = public_issue["html_url"]
    author = public_issue["user"]["login"]
    node_id = public_issue["node_id"]
    body = public_issue.get("body") or ""

    lines = [
        f"**Public issue**: {url}",
        f"**Author**: @{author}",
        "",
        BEGIN_PUBLIC_BODY,
        body,
        END_PUBLIC_BODY,
        "",
        f"<!-- public_issue_url: {url} -->",
        f"<!-- public_issue_node_id: {node_id} -->",
    ]
    return "\n".join(lines)


def build_private_issue_title(public_issue: dict) -> str:
    """Build the private issue title: [public #N] <title>."""
    return f"[public #{public_issue['number']}] {public_issue['title']}"


def parse_private_body_markers(body: str) -> tuple[str, str] | None:
    """Extract (public_url, public_node_id) from a private issue body."""
    url_match = PUBLIC_BODY_URL_RE.search(body)
    node_match = PUBLIC_BODY_NODE_ID_RE.search(body)
    if url_match and node_match:
        return url_match.group(1), node_match.group(1)
    return None


def public_number_from_url(url: str) -> int:
    """Extract the issue number from a public issue URL."""
    return int(url.rstrip("/").split("/")[-1])


def update_private_body_public_section(private_body: str, new_public_body: str) -> str:
    """Replace content between BEGIN/END PUBLIC BODY delimiters."""
    begin_idx = private_body.find(BEGIN_PUBLIC_BODY)
    end_idx = private_body.find(END_PUBLIC_BODY)
    if begin_idx == -1 or end_idx == -1:
        return private_body
    return (
        private_body[:begin_idx]
        + BEGIN_PUBLIC_BODY
        + "\n"
        + new_public_body
        + "\n"
        + private_body[end_idx:]
    )


def build_mirrored_comment_body(
    author: str, permalink: str, body: str, public_comment_id: int
) -> str:
    """Build a mirrored private comment body."""
    return (
        f"From @{author} at {permalink}:\n\n"
        f"{body}\n\n"
        f"<!-- public_comment_id: {public_comment_id} -->"
    )


def build_tombstone_comment_body(
    author: str, permalink: str, timestamp: str, public_comment_id: int
) -> str:
    """Build a tombstone for a deleted public comment."""
    return (
        f"From @{author} at {permalink}:\n\n"
        f"*(deleted on public at {timestamp})*\n\n"
        f"<!-- public_comment_id: {public_comment_id} -->"
    )


def parse_public_comment_id(body: str) -> int | None:
    """Extract the public_comment_id from a mirrored private comment."""
    m = PUBLIC_COMMENT_ID_RE.search(body)
    return int(m.group(1)) if m else None


# ── API-dependent resolution ────────────────────────────────────────────────

def find_mapping_in_comments(comments: list) -> tuple[str, int] | None:
    """Scan comments for the mapping marker. Returns (node_id, private_number)."""
    for comment in comments:
        body = comment.body if hasattr(comment, "body") else comment.get("body", "")
        result = parse_mapping_comment(body)
        if result:
            return result
    return None


def resolve_mapping(
    client: Github, config: Config, public_issue: dict
) -> PrivateMapping | None:
    """3-step lookup: mapping comment → fallback body search → None.

    If fallback succeeds, self-heals by re-posting the mapping comment.
    """
    node_id = public_issue["node_id"]
    public_number = public_issue["number"]

    # Step 1: Check mapping comment on public issue
    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)
    comments = list(pub_issue.get_comments())
    mapping = find_mapping_in_comments(comments)
    if mapping:
        _, private_number = mapping
        priv_repo = client.get_repo(config.private_repo)
        private_issue = priv_repo.get_issue(private_number)
        return PrivateMapping(
            private_issue=private_issue,
            private_issue_number=private_number,
        )

    # Step 2: Fallback — search private issue bodies for the node_id
    priv_repo = client.get_repo(config.private_repo)
    for issue in priv_repo.get_issues(state="all"):
        body = issue.body or ""
        markers = parse_private_body_markers(body)
        if markers and markers[1] == node_id:
            # Self-heal: re-post mapping comment on public issue
            mapping_text = build_mapping_comment(config, node_id, issue.number)
            pub_issue.create_comment(mapping_text)
            logger.info(
                "Self-healed mapping comment for public #%d -> private #%d",
                public_number,
                issue.number,
            )
            return PrivateMapping(
                private_issue=issue,
                private_issue_number=issue.number,
                was_self_healed=True,
            )

    # Step 3: No mapping found
    return None


def find_mirrored_comment(
    private_issue: Issue, public_comment_id: int
) -> IssueComment | None:
    """Find the mirrored private comment for a given public comment ID."""
    for comment in private_issue.get_comments():
        cid = parse_public_comment_id(comment.body or "")
        if cid == public_comment_id:
            return comment
    return None
