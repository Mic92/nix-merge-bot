import logging
import re
from typing import Any

from nixpkgs_merge_bot.commands.merge import merge_command
from nixpkgs_merge_bot.github.issue import IssueComment
from nixpkgs_merge_bot.settings import Settings

from .http_response import HttpResponse
from .utils.issue_response import issue_response

log = logging.getLogger(__name__)


def process_comment(issue: IssueComment, settings: Settings) -> HttpResponse:
    log.debug(issue)
    # ignore our own comments and comments from other bots (security)
    if issue.is_bot:
        log.debug(f"{issue.issue_number}: ignoring event as it is from a bot")
        return issue_response("ignore-bot")
    if not issue.is_pull_request:
        log.debug(f"{issue.issue_number}: ignoring event as it is not a pull request")
        return issue_response("ignore-not-pr")

    if issue.action not in ("created", "edited", "submitted"):
        log.debug(
            f"{issue.issue_number}: ignoring event as actions is not created, edited or submitted"
        )
        return issue_response("ignore-action")

    if issue.text is not None:
        stripped = re.sub("(<!--.*?-->)", "", issue.text, flags=re.DOTALL)
        stripped = re.sub("(```.*?```)", "", stripped, flags=re.DOTALL)
        bot_name = re.escape(settings.bot_name)
        for line in stripped.split("\n"):
            if re.match(rf"^@{bot_name}\s+merge$", line.strip()):
                return merge_command(issue, settings)
        log.debug(f"{issue.issue_number}: no command was found in comment")
        return issue_response("no-command")
    log.debug(f"{issue.issue_number}: comment was empty")
    return issue_response("no-command")


def issue_comment(body: dict[str, Any], settings: Settings) -> HttpResponse:
    log.debug("issue_comment")
    issue = IssueComment.from_issue_comment_json(body)
    return process_comment(issue, settings)


def review_comment(body: dict[str, Any], settings: Settings) -> HttpResponse:
    log.debug("review_comment")
    issue = IssueComment.from_review_comment_json(body)
    return process_comment(issue, settings)


def review(body: dict[str, Any], settings: Settings) -> HttpResponse:
    log.debug("review")
    issue = IssueComment.from_review_json(body)
    return process_comment(issue, settings)
