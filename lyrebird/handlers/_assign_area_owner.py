"""Shared helper: assign an area's default owner to an unassigned private issue.

Lyrebird ignores events sent by its own App identity, so a label the bot applies
never comes back as a `labeled` event. Every site that puts an area label on a
private issue therefore has to run the assignment itself.
"""

from __future__ import annotations

import logging
from typing import Iterable

from github import Github

from lyrebird.config import Config
from lyrebird.loop_prevention import is_bot_login

logger = logging.getLogger(__name__)


def _first_mapped_area(
    config: Config, label_names: Iterable[str]
) -> tuple[str, str] | None:
    """Return (label_name, login) for the first name with a configured owner."""
    for name in label_names:
        login = config.assignee_for_area(name)
        if login:
            return name, login
    return None


def _safe_number(priv_issue) -> int | str:
    """Return the issue number for log messages, or '?' when reading it fails.

    The error path cannot re-read `.number`: the transient API failure that put
    us there completes every other attribute the same way, and `getattr`'s
    default only covers AttributeError.
    """
    try:
        return priv_issue.number
    except Exception:
        return "?"


def _assignment_confirmed(priv_issue, login) -> bool:
    """Say whether *login* shows up in the issue's refreshed assignee list.

    `add_to_assignees` rewrites the issue in place from the POST response body,
    so this reads GitHub's own view of the outcome at no extra API call.  A
    warning here names one person's account, so anything unreadable counts as
    confirmation: only a list read end to end that lacks the login is evidence
    the assignment was dropped.  Logins compare case-insensitively, since the
    response carries the account's own spelling rather than the configured one.
    """
    try:
        assignees = priv_issue.assignees
        if assignees is None:
            return True
        wanted = login.casefold()
        unreadable = False
        for assignee in assignees:
            try:
                if assignee.login.casefold() == wanted:
                    return True
            except Exception:
                unreadable = True
        return unreadable
    except Exception:
        return True


def _concurrent_assignees(priv_issue, login) -> list[str] | None:
    """Return readable co-assignees, or None when the state is uncertain."""
    try:
        assignees = priv_issue.assignees
        if assignees is None:
            return None
        wanted = login.casefold()
        co_assignees = []
        for assignee in assignees:
            try:
                assignee_login = assignee.login
                if assignee_login.casefold() != wanted:
                    co_assignees.append(assignee_login)
            except Exception:
                # An incomplete response is uncertain, so do not remove a good assignment.
                return None
        return co_assignees
    except Exception:
        return None


def _bot_assignment_provenance(config: Config, priv_issue, login: str) -> bool:
    """Say whether the bot made the latest assignment change for *login*.

    Re-adding an already-assigned login is a no-op that emits no new assigned
    event, so the latest assigned event for the login reflects who actually
    caused the current assignment.
    """
    try:
        last_matching_action = last_matching_assigner = None
        wanted = login.casefold()
        for issue_event in priv_issue.get_events():
            action = issue_event.event
            if action not in ("assigned", "unassigned"):
                continue
            if issue_event.assignee.login.casefold() != wanted:
                continue
            last_matching_action = action
            last_matching_assigner = issue_event.assigner.login
        return (
            last_matching_action == "assigned"
            and is_bot_login(config, last_matching_assigner)
        )
    except Exception:
        return False


def assign_area_owner(
    config: Config, priv_issue, label_names: Iterable[str]
) -> str | None:
    """Assign the area owner for the first mapped label in *label_names*.

    Only open issues with no assignee are touched, so an existing assignment is
    never overridden.  Returns the login assigned, or None when nothing was
    assigned, which includes an assignment GitHub accepts and then silently
    drops.  Every failure is contained here: callers must not add a second
    try/except of their own.  *label_names* is scanned once, so a one-shot
    iterable is fine.  GitHub has no conditional assignment and assigning
    workflows are not mutually serialized, so the guard is check-then-act: a
    detected race yields only when the issue events prove the bot made the
    assignment.  A human-caused or unprovable assignment is never touched.
    The final one-request window cannot be closed by this API, so a double
    yield can still end unassigned; it is detected and warned rather than
    prevented.
    """
    label_name = "?"
    login = "?"
    issue_id: int | str = "?"

    try:
        match = _first_mapped_area(config, label_names)
        if match is None:
            # No area label (or no owner configured); nothing to do.
            return None
        label_name, login = match
        # Read the number only once a mapped label is in hand, so an unmapped
        # label still costs no API call on a lazily completed issue.
        issue_id = _safe_number(priv_issue)

        if priv_issue.state != "open":
            logger.info(
                "Private #%s is %s; skipping area assignment for '%s'",
                issue_id,
                priv_issue.state,
                label_name,
            )
            return None
        if priv_issue.assignees:
            logger.info(
                "Private #%s already assigned; leaving area owner untouched",
                issue_id,
            )
            return None
        priv_issue.add_to_assignees(login)
        if not _assignment_confirmed(priv_issue, login):
            logger.warning(
                "GitHub dropped the assignment of '%s' to private #%s for area "
                "label '%s'; the login may have no push access on the private repo",
                login,
                issue_id,
                label_name,
            )
            return None
        co_assignees = _concurrent_assignees(priv_issue, login)
        if co_assignees is None:
            logger.warning(
                "The post-write assignee state could not be verified for private #%s; keeping '%s' assigned",
                issue_id,
                login,
            )
            return login
        if co_assignees:
            # Event history is fetched only for this rare post-write conflict.
            if not _bot_assignment_provenance(config, priv_issue, login):
                logger.warning(
                    "Private #%s now has multiple assignees after the bot added '%s': %s; may need manual attention",
                    issue_id,
                    login,
                    ", ".join([login, *co_assignees]),
                )
                return None
            try:
                priv_issue.update()
            except Exception:
                logger.warning(
                    "The post-write assignee state could not be verified for private #%s; keeping '%s' assigned",
                    issue_id,
                    login,
                    exc_info=True,
                )
                return login
            co_assignees = _concurrent_assignees(priv_issue, login)
            if co_assignees is None:
                logger.warning(
                    "The post-write assignee state could not be verified for private #%s; keeping '%s' assigned",
                    issue_id,
                    login,
                )
                return login
            if not co_assignees:
                if not _assignment_confirmed(priv_issue, login):
                    logger.warning(
                        "Private #%s ended unassigned after concurrent yields and needs manual attention",
                        issue_id,
                    )
                    return None
                logger.info(
                    "Assigned '%s' to private #%s for area label '%s'",
                    login,
                    issue_id,
                    label_name,
                )
                return login
            try:
                priv_issue.remove_from_assignees(login)
            except Exception:
                logger.warning(
                    "Private #%s removal attempt for '%s' failed with outcome unknown; the issue's assignees need manual verification",
                    issue_id,
                    login,
                    exc_info=True,
                )
                return None
            try:
                assignees_after_removal = priv_issue.assignees
            except Exception:
                logger.warning(
                    "The post-removal assignee state could not be verified for private #%s; needs manual verification",
                    issue_id,
                    exc_info=True,
                )
                return None
            if assignees_after_removal is None:
                logger.warning(
                    "The post-removal assignee state could not be verified for private #%s; needs manual verification",
                    issue_id,
                )
                return None
            if not assignees_after_removal:
                # Re-adding can reopen the race as assignment ping-pong.
                logger.warning(
                    "Private #%s ended unassigned after concurrent yields and needs manual attention",
                    issue_id,
                )
                return None
            logger.warning(
                "Private #%s assignment of '%s' yielded to concurrent assignee(s) %s",
                issue_id,
                login,
                ", ".join(co_assignees),
            )
            return None
        logger.info(
            "Assigned '%s' to private #%s for area label '%s'",
            login,
            issue_id,
            label_name,
        )
    except Exception:
        logger.exception(
            "Failed to assign '%s' to private #%s for area label '%s'",
            login,
            issue_id,
            label_name,
        )
        return None
    return login


def assign_area_owner_by_number(
    client: Github, config: Config, issue_number: int, label_names: Iterable[str]
) -> str | None:
    """Fetch private issue *issue_number*, then delegate to assign_area_owner.

    For callers that hold only a webhook payload dict, or whose issue object
    may be stale.  The mapped-label check runs first so a label with no owner
    costs no API call, and it runs on a materialised copy so a one-shot
    iterable survives the second scan the delegate makes.  Neither the check
    nor the fetch can abort the caller, and the delegate contains its own
    failures.
    """
    try:
        names = list(label_names)
        if _first_mapped_area(config, names) is None:
            return None
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue_number)
    except Exception:
        logger.exception(
            "Could not fetch private #%s for area assignment", issue_number
        )
        return None
    return assign_area_owner(config, priv_issue, names)
