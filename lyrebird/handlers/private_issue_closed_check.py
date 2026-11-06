"""Delayed close check: complete issues closed by code or nudge for a resolution."""

from __future__ import annotations

import logging
from datetime import datetime

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._post_resolution import post_resolution
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

logger = logging.getLogger(__name__)


def _code_closer_url(
    client: Github, repo_full_name: str, issue_number: int
) -> str | None:
    try:
        owner, name = repo_full_name.split("/")
        _, response = client.requester.graphql_query(
            """
            query($owner: String!, $name: String!, $number: Int!) {
              repository(owner: $owner, name: $name) {
                issue(number: $number) {
                  timelineItems(itemTypes: [CLOSED_EVENT], last: 1) {
                    nodes {
                      ... on ClosedEvent {
                        closer {
                          __typename
                          ... on PullRequest { url }
                          ... on Commit { url }
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"owner": owner, "name": name, "number": issue_number},
        )
        nodes = response["data"]["repository"]["issue"]["timelineItems"]["nodes"]
        closer = nodes[-1]["closer"]
        if closer and closer["__typename"] in {"PullRequest", "Commit"}:
            return closer["url"]
    except Exception as exc:
        logger.warning(
            "Could not look up closer for %s#%d: %s",
            repo_full_name, issue_number, exc,
        )
    return None


def _nudge_message(config: Config, public_url: str, present: set[str]) -> str:
    public_issue = f"Public issue [#{public_number_from_url(public_url)}]({public_url})"
    if len(present) > 1:
        labels = ", ".join(f"`{name}`" for name in sorted(present))
        return (
            f"{public_issue} was closed with no note because this "
            f"issue has {len(present)} resolution labels ({labels}). "
            "Remove them all, then add the one you want; adding it posts its note."
        )

    offered = [
        f"`{name}`"
        for name, note, _ in config.resolution_labels.values()
        if note and name != config.needs_resolution_label
    ]
    allowed = (
        ", ".join(offered[:-1]) + " or " + offered[-1]
        if len(offered) > 1
        else "".join(offered)
    )
    return (
        f"{public_issue} was closed with no note. "
        f"To post one, add a resolution label: {allowed}. "
        "To write your own note instead, comment `/anon <message>` here."
    )


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    markers = parse_private_body_markers(issue_body)
    if markers is None:
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    # Bail if reopened during grace period
    if priv_issue.state != "closed":
        logger.info(
            "Private #%d reopened during grace period, skipping nudge",
            issue["number"],
        )
        return

    # Count resolution labels (excluding resolution:none itself)
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = {lbl.name for lbl in priv_issue.get_labels()}
    resolution_labels_present = (
        current_labels & all_resolution_labels
    ) - {config.needs_resolution_label}

    if len(resolution_labels_present) == 1:
        # Already handled by close handler or label handler
        return

    completed_label = config.resolution_label_name("completed")
    if not resolution_labels_present and completed_label:
        closer_url = _code_closer_url(client, config.private_repo, issue["number"])
        if closer_url:
            public_url, _ = markers
            public_number = public_number_from_url(public_url)
            pub_issue = client.get_repo(config.public_repo).get_issue(public_number)
            priv_issue = priv_repo.get_issue(issue["number"])
            if priv_issue.state != "closed":
                return
            closed_at = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
            if priv_issue.closed_at != closed_at:
                return
            current_labels = {lbl.name for lbl in priv_issue.labels}
            resolution_labels_present = (
                current_labels & all_resolution_labels
            ) - {config.needs_resolution_label}
            if len(resolution_labels_present) == 1:
                return
            if not resolution_labels_present:
                post_resolution(config, priv_issue, pub_issue, "completed", current_labels)
                priv_issue.add_to_labels(completed_label)
                priv_issue.create_comment(
                    f"Closed by {closer_url}: marked `{completed_label}` and posted "
                    f"its note on public issue [#{public_number}]({public_url})."
                )
                logger.info(
                    "Private #%d closed by %s, posted completed resolution on public #%d",
                    issue["number"], closer_url, public_number,
                )
                return

    if config.needs_resolution_label not in current_labels:
        priv_issue.add_to_labels(config.needs_resolution_label)

    msg = _nudge_message(config, markers[0], resolution_labels_present)
    priv_issue.create_comment(msg)
    logger.info(
        "Private #%d closed with %d resolution labels, nudged after grace period",
        issue["number"],
        len(resolution_labels_present),
    )
