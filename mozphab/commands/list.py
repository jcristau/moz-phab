# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json

from mozphab.conduit import conduit
from mozphab.exceptions import Error
from mozphab.logger import logger
from mozphab.spinner import wait_message


def format_revision_status(status: str) -> str:
    """Format status string for display."""
    status_colors = {
        "needs-review": "Needs Review",
        "needs-revision": "Needs Revision",
        "accepted": "Accepted",
        "changes-planned": "Changes Planned",
        "abandoned": "Abandoned",
        "published": "Published",
    }
    return status_colors.get(status, status.title())


def list_revisions(repo, args: argparse.Namespace):
    """List in-flight patches for the current user."""

    # Check connection to Phabricator
    with wait_message("Checking connection to Phabricator..."):
        if not conduit.check():
            raise Error("Failed to use Conduit API")

    # Get current user's PHID
    with wait_message("Fetching user information..."):
        whoami = conduit.whoami()
        user_phid = whoami.get("phid")
        if not user_phid:
            raise Error("Unable to determine current user")

    # Build status filter based on flags
    if args.status:
        # User explicitly specified statuses
        status_filter = args.status
    else:
        # Build default status list (exclude abandoned and closed by default)
        status_filter = [
            "needs-review",
            "needs-revision",
            "accepted",
            "changes-planned",
        ]

        if args.include_abandoned:
            status_filter.append("abandoned")

        if args.all:
            # Include published/closed statuses
            status_filter.append("published")

    # Query revisions authored by the current user
    api_call_args = {
        "constraints": {
            "authorPHIDs": [user_phid],
            "statuses": status_filter,
        },
        "attachments": {
            "reviewers": True,
        },
        "order": "updated",
    }

    with wait_message("Fetching revisions..."):
        response = conduit.call("differential.revision.search", api_call_args)
        revisions = response.get("data", [])

    if not revisions:
        if args.format == "json":
            print(json.dumps([], indent=2))
        else:
            logger.info("No in-flight revisions found.")
        return

    # Format as JSON if requested
    if args.format == "json":
        output_data = []
        for revision in revisions:
            rev_id = revision["id"]
            fields = revision["fields"]

            # Build JSON object
            rev_data = {
                "id": rev_id,
                "title": fields["title"],
                "status": fields["status"]["value"],
                "uri": fields.get("uri", f"D{rev_id}"),
                "dateCreated": fields.get("dateCreated"),
                "dateModified": fields.get("dateModified"),
            }

            # Add reviewers if verbose
            if args.verbose:
                reviewers_data = revision["attachments"]["reviewers"]["reviewers"]
                rev_data["reviewers"] = [
                    {
                        "phid": r.get("reviewerPHID"),
                        "status": r.get("status"),
                        "isBlocking": r.get("isBlocking", False),
                    }
                    for r in reviewers_data
                ]

            output_data.append(rev_data)

        print(json.dumps(output_data, indent=2))
        return

    # Display results in human-readable format
    logger.info("In-flight revisions:\n")

    for revision in revisions:
        rev_id = revision["id"]
        fields = revision["fields"]
        title = fields["title"]
        status = fields["status"]["value"]
        status_display = format_revision_status(status)

        # Get reviewer info
        reviewers_data = revision["attachments"]["reviewers"]["reviewers"]
        reviewers = []
        for reviewer in reviewers_data:
            reviewer_status = reviewer.get("status", "")
            if reviewer_status == "accepted":
                reviewers.append(f"✓ {reviewer.get('reviewerPHID', '')}")
            elif reviewer_status == "rejected":
                reviewers.append(f"✗ {reviewer.get('reviewerPHID', '')}")
            else:
                reviewers.append(reviewer.get("reviewerPHID", ""))

        # Format output
        logger.info(f"D{rev_id}: {title}")
        logger.info(f"  Status: {status_display}")
        if reviewers and args.verbose:
            logger.info(f"  Reviewers: {', '.join(reviewers[:3])}")  # Show first 3
        logger.info("")

    logger.info(f"Total: {len(revisions)} revision(s)")


def add_parser(parser):
    """Add the list command parser."""
    list_parser = parser.add_parser(
        "list",
        help="List in-flight patches for the current user.",
    )
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include closed (landed) revisions (default: False).",
    )
    list_parser.add_argument(
        "--include-abandoned",
        action="store_true",
        help="Include abandoned revisions (default: False).",
    )
    list_parser.add_argument(
        "--status",
        nargs="+",
        choices=[
            "needs-review",
            "needs-revision",
            "accepted",
            "changes-planned",
            "abandoned",
            "published",
        ],
        help="Filter by specific status(es).",
    )
    list_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show additional information like reviewers (default: False).",
    )
    list_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    list_parser.add_argument(
        "--safe-mode",
        dest="safe_mode",
        action="store_true",
        help="Run VCS with only necessary extensions.",
    )
    list_parser.set_defaults(func=list_revisions, needs_repo=True)
