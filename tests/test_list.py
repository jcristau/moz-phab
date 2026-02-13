# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import unittest
from unittest import mock

from callee import Contains

from mozphab import exceptions
from mozphab.commands import list as list_command


class TestFormatRevisionStatus(unittest.TestCase):
    """Test the status formatting functionality."""

    def test_format_known_statuses(self):
        """Test formatting of known status values."""
        self.assertEqual(
            list_command.format_revision_status("needs-review"), "Needs Review"
        )
        self.assertEqual(
            list_command.format_revision_status("needs-revision"), "Needs Revision"
        )
        self.assertEqual(list_command.format_revision_status("accepted"), "Accepted")
        self.assertEqual(
            list_command.format_revision_status("changes-planned"), "Changes Planned"
        )
        self.assertEqual(list_command.format_revision_status("abandoned"), "Abandoned")
        self.assertEqual(list_command.format_revision_status("published"), "Published")

    def test_format_unknown_status(self):
        """Test formatting of unknown status values."""
        # Should title-case unknown statuses
        self.assertEqual(
            list_command.format_revision_status("some-status"), "Some-Status"
        )


class TestListRevisions(unittest.TestCase):
    """Test the main list functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.args = argparse.Namespace(
            all=False,
            include_abandoned=False,
            status=None,
            verbose=False,
            format="text",
            user=None,
        )
        self.mock_revisions = [
            {
                "id": 123,
                "phid": "PHID-DREV-123",
                "fields": {
                    "title": "Test revision 123",
                    "status": {"value": "needs-review", "closed": False},
                    "uri": "https://phabricator.services.mozilla.com/D123",
                    "dateCreated": 1234567890,
                    "dateModified": 1234567900,
                },
                "attachments": {
                    "reviewers": {
                        "reviewers": [
                            {
                                "reviewerPHID": "PHID-USER-1",
                                "status": "added",
                                "isBlocking": False,
                            }
                        ]
                    }
                },
            },
            {
                "id": 124,
                "phid": "PHID-DREV-124",
                "fields": {
                    "title": "Test revision 124",
                    "status": {"value": "accepted", "closed": False},
                    "uri": "https://phabricator.services.mozilla.com/D124",
                    "dateCreated": 1234567891,
                    "dateModified": 1234567901,
                },
                "attachments": {
                    "reviewers": {
                        "reviewers": [
                            {
                                "reviewerPHID": "PHID-USER-2",
                                "status": "accepted",
                                "isBlocking": True,
                            }
                        ]
                    }
                },
            },
            {
                "id": 125,
                "phid": "PHID-DREV-125",
                "fields": {
                    "title": "Test revision 125",
                    "status": {"value": "abandoned", "closed": False},
                    "uri": "https://phabricator.services.mozilla.com/D125",
                    "dateCreated": 1234567892,
                    "dateModified": 1234567902,
                },
                "attachments": {"reviewers": {"reviewers": []}},
            },
            {
                "id": 126,
                "phid": "PHID-DREV-126",
                "fields": {
                    "title": "Test revision 126 - closed",
                    "status": {"value": "published", "closed": True},
                    "uri": "https://phabricator.services.mozilla.com/D126",
                    "dateCreated": 1234567893,
                    "dateModified": 1234567903,
                },
                "attachments": {"reviewers": {"reviewers": []}},
            },
        ]

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_success(self, mock_conduit):
        """Test successful listing of revisions."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {
            "data": [self.mock_revisions[0], self.mock_revisions[1]]
        }

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify API calls
        mock_conduit.check.assert_called_once()
        mock_conduit.whoami.assert_called_once()
        mock_conduit.call.assert_called_once()

        # Verify the API call arguments
        call_args = mock_conduit.call.call_args
        self.assertEqual(call_args[0][0], "differential.revision.search")
        self.assertIn("authorPHIDs", call_args[0][1]["constraints"])
        self.assertEqual(
            call_args[0][1]["constraints"]["authorPHIDs"], ["PHID-USER-test"]
        )

        # Verify output
        self.assertIn(Contains("D123"), logging_watcher.output)
        self.assertIn(Contains("D124"), logging_watcher.output)
        self.assertIn(Contains("Total: 2 revision(s)"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_filters_closed(self, mock_conduit):
        """Test that closed revisions are filtered by default."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        # Mock API returns only non-closed, non-abandoned revisions (server-side filtering)
        mock_conduit.call.return_value = {
            "data": [self.mock_revisions[0], self.mock_revisions[1]]
        }

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify the API was called with correct status filter
        call_args = mock_conduit.call.call_args
        self.assertIn("statuses", call_args[0][1]["constraints"])
        statuses = call_args[0][1]["constraints"]["statuses"]
        self.assertNotIn("published", statuses)
        self.assertNotIn("abandoned", statuses)

        # Verify closed revision is not shown
        self.assertNotIn(Contains("D126"), logging_watcher.output)
        # Verify open revisions are shown
        self.assertIn(Contains("D123"), logging_watcher.output)
        self.assertIn(Contains("D124"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_filters_abandoned(self, mock_conduit):
        """Test that abandoned revisions are filtered by default."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        # Mock API returns only non-abandoned, non-closed revisions (server-side filtering)
        mock_conduit.call.return_value = {
            "data": [self.mock_revisions[0], self.mock_revisions[1]]
        }

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify the API was called with correct status filter
        call_args = mock_conduit.call.call_args
        self.assertIn("statuses", call_args[0][1]["constraints"])
        statuses = call_args[0][1]["constraints"]["statuses"]
        self.assertNotIn("abandoned", statuses)

        # Verify abandoned revision is not shown
        self.assertNotIn(Contains("D125"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_include_all(self, mock_conduit):
        """Test listing with --all flag includes closed revisions."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        # Mock API returns all revisions including closed (because --all is set)
        mock_conduit.call.return_value = {"data": self.mock_revisions}

        # Modify args to include all
        self.args.all = True

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify the API was called with status filter including published
        call_args = mock_conduit.call.call_args
        self.assertIn("statuses", call_args[0][1]["constraints"])
        statuses = call_args[0][1]["constraints"]["statuses"]
        self.assertIn("published", statuses)

        # Verify closed revision is now shown
        self.assertIn(Contains("D126"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_include_abandoned(self, mock_conduit):
        """Test listing with --include-abandoned flag."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        # Mock API returns revisions including abandoned (because --include-abandoned is set)
        mock_conduit.call.return_value = {
            "data": [
                self.mock_revisions[0],
                self.mock_revisions[1],
                self.mock_revisions[2],
            ]
        }

        # Modify args to include abandoned
        self.args.include_abandoned = True

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify the API was called with status filter including abandoned
        call_args = mock_conduit.call.call_args
        self.assertIn("statuses", call_args[0][1]["constraints"])
        statuses = call_args[0][1]["constraints"]["statuses"]
        self.assertIn("abandoned", statuses)

        # Verify abandoned revision is now shown
        self.assertIn(Contains("D125"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_status_filter(self, mock_conduit):
        """Test listing with status filter."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": [self.mock_revisions[1]]}

        # Modify args to filter by status
        self.args.status = ["accepted"]

        # Call function
        list_command.list_revisions(None, self.args)

        # Verify the API call includes status constraint
        call_args = mock_conduit.call.call_args
        self.assertIn("statuses", call_args[0][1]["constraints"])
        self.assertEqual(call_args[0][1]["constraints"]["statuses"], ["accepted"])

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_no_results(self, mock_conduit):
        """Test listing when no revisions are found."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": []}

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify message
        self.assertIn(Contains("No in-flight revisions found"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_connection_failure(self, mock_conduit):
        """Test handling of connection failures."""
        mock_conduit.check.return_value = False

        with self.assertRaises(exceptions.Error) as cm:
            list_command.list_revisions(None, self.args)

        self.assertIn("Failed to use Conduit API", str(cm.exception))

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_no_user_phid(self, mock_conduit):
        """Test handling when user PHID cannot be determined."""
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {}  # No PHID

        with self.assertRaises(exceptions.Error) as cm:
            list_command.list_revisions(None, self.args)

        self.assertIn("Unable to determine current user", str(cm.exception))

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_verbose(self, mock_conduit):
        """Test listing with verbose flag shows reviewers."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": [self.mock_revisions[1]]}

        # Modify args to be verbose
        self.args.verbose = True

        # Call function
        with self.assertLogs() as logging_watcher:
            list_command.list_revisions(None, self.args)

        # Verify reviewer information is shown
        self.assertIn(Contains("Reviewers:"), logging_watcher.output)

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_specified_user(self, mock_conduit):
        """Test listing with --user flag."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.get_users.return_value = [
            {"phid": "PHID-USER-other", "userName": "otheruser"}
        ]
        mock_conduit.call.return_value = {"data": [self.mock_revisions[0]]}

        # Modify args to specify a user
        self.args.user = "otheruser"

        # Call function
        with self.assertLogs():
            list_command.list_revisions(None, self.args)

        # Verify get_users was called with the username
        mock_conduit.get_users.assert_called_once_with(["otheruser"])

        # Verify whoami was NOT called
        mock_conduit.whoami.assert_not_called()

        # Verify the API call used the other user's PHID
        call_args = mock_conduit.call.call_args
        self.assertIn("authorPHIDs", call_args[0][1]["constraints"])
        self.assertEqual(
            call_args[0][1]["constraints"]["authorPHIDs"], ["PHID-USER-other"]
        )

    @mock.patch("mozphab.commands.list.conduit")
    def test_list_revisions_user_not_found(self, mock_conduit):
        """Test handling when specified user is not found."""
        mock_conduit.check.return_value = True
        mock_conduit.get_users.return_value = []

        # Modify args to specify a non-existent user
        self.args.user = "nonexistent"

        with self.assertRaises(exceptions.Error) as cm:
            list_command.list_revisions(None, self.args)

        self.assertIn("User not found: nonexistent", str(cm.exception))


class TestListRevisionsJSON(unittest.TestCase):
    """Test JSON output format."""

    def setUp(self):
        """Set up test fixtures."""
        self.args = argparse.Namespace(
            all=False,
            include_abandoned=False,
            status=None,
            verbose=False,
            format="json",
            user=None,
        )
        self.mock_revisions = [
            {
                "id": 123,
                "phid": "PHID-DREV-123",
                "fields": {
                    "title": "Test revision 123",
                    "status": {"value": "needs-review", "closed": False},
                    "uri": "https://phabricator.services.mozilla.com/D123",
                    "dateCreated": 1234567890,
                    "dateModified": 1234567900,
                },
                "attachments": {
                    "reviewers": {
                        "reviewers": [
                            {
                                "reviewerPHID": "PHID-USER-1",
                                "status": "added",
                                "isBlocking": False,
                            }
                        ]
                    }
                },
            },
            {
                "id": 124,
                "phid": "PHID-DREV-124",
                "fields": {
                    "title": "Test revision 124",
                    "status": {"value": "accepted", "closed": False},
                    "uri": "https://phabricator.services.mozilla.com/D124",
                    "dateCreated": 1234567891,
                    "dateModified": 1234567901,
                },
                "attachments": {
                    "reviewers": {
                        "reviewers": [
                            {
                                "reviewerPHID": "PHID-USER-2",
                                "status": "accepted",
                                "isBlocking": True,
                            }
                        ]
                    }
                },
            },
        ]

    @mock.patch("mozphab.commands.list.conduit")
    @mock.patch("builtins.print")
    def test_list_json_format(self, mock_print, mock_conduit):
        """Test JSON output format."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": self.mock_revisions}

        # Call function
        list_command.list_revisions(None, self.args)

        # Verify print was called with JSON
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]

        # Verify it's valid JSON
        parsed = json.loads(output)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], 123)
        self.assertEqual(parsed[0]["title"], "Test revision 123")
        self.assertEqual(parsed[0]["status"], "needs-review")
        self.assertEqual(
            parsed[0]["uri"], "https://phabricator.services.mozilla.com/D123"
        )

    @mock.patch("mozphab.commands.list.conduit")
    @mock.patch("builtins.print")
    def test_list_json_format_verbose(self, mock_print, mock_conduit):
        """Test JSON output format with verbose flag."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": self.mock_revisions}

        # Modify args to be verbose
        self.args.verbose = True

        # Call function
        list_command.list_revisions(None, self.args)

        # Verify print was called with JSON
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]

        # Verify it's valid JSON with reviewers
        parsed = json.loads(output)
        self.assertIn("reviewers", parsed[0])
        self.assertEqual(len(parsed[0]["reviewers"]), 1)
        self.assertEqual(parsed[0]["reviewers"][0]["phid"], "PHID-USER-1")
        self.assertEqual(parsed[0]["reviewers"][0]["status"], "added")
        self.assertFalse(parsed[0]["reviewers"][0]["isBlocking"])

    @mock.patch("mozphab.commands.list.conduit")
    @mock.patch("builtins.print")
    def test_list_json_empty_results(self, mock_print, mock_conduit):
        """Test JSON output with no results."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": []}

        # Call function
        list_command.list_revisions(None, self.args)

        # Verify print was called with empty JSON array
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        parsed = json.loads(output)
        self.assertEqual(parsed, [])

    @mock.patch("mozphab.commands.list.conduit")
    @mock.patch("builtins.print")
    def test_list_json_no_spinner(self, mock_print, mock_conduit):
        """Test that JSON format doesn't produce spinner output."""
        # Setup mocks
        mock_conduit.check.return_value = True
        mock_conduit.whoami.return_value = {"phid": "PHID-USER-test"}
        mock_conduit.call.return_value = {"data": self.mock_revisions}

        # Call function - should not produce logs
        list_command.list_revisions(None, self.args)

        # Only print should be called (for JSON output)
        mock_print.assert_called_once()


class TestListParser(unittest.TestCase):
    """Test the argument parser setup."""

    def test_add_parser(self):
        """Test that the parser is configured correctly."""
        # Create a parent parser to add our command to
        parent_parser = argparse.ArgumentParser()
        subparsers = parent_parser.add_subparsers()

        # Add our list parser
        list_command.add_parser(subparsers)

        # Test parsing with defaults
        args = parent_parser.parse_args(["list"])
        self.assertFalse(args.all)
        self.assertFalse(args.include_abandoned)
        self.assertIsNone(args.status)
        self.assertFalse(args.verbose)
        self.assertEqual(args.format, "text")

        # Test with --all flag
        args = parent_parser.parse_args(["list", "--all"])
        self.assertTrue(args.all)

        # Test with --include-abandoned flag
        args = parent_parser.parse_args(["list", "--include-abandoned"])
        self.assertTrue(args.include_abandoned)

        # Test with --status flag
        args = parent_parser.parse_args(["list", "--status", "accepted"])
        self.assertEqual(args.status, ["accepted"])

        # Test with multiple statuses
        args = parent_parser.parse_args(
            ["list", "--status", "accepted", "needs-review"]
        )
        self.assertEqual(args.status, ["accepted", "needs-review"])

        # Test with --verbose flag
        args = parent_parser.parse_args(["list", "--verbose"])
        self.assertTrue(args.verbose)

        # Test with -v flag
        args = parent_parser.parse_args(["list", "-v"])
        self.assertTrue(args.verbose)

        # Test with --format flag
        args = parent_parser.parse_args(["list", "--format", "json"])
        self.assertEqual(args.format, "json")

        # Test with --user flag
        args = parent_parser.parse_args(["list", "--user", "testuser"])
        self.assertEqual(args.user, "testuser")

        # Test combined flags
        args = parent_parser.parse_args(
            [
                "list",
                "--all",
                "--verbose",
                "--format",
                "json",
                "--status",
                "accepted",
                "--user",
                "otheruser",
            ]
        )
        self.assertTrue(args.all)
        self.assertTrue(args.verbose)
        self.assertEqual(args.format, "json")
        self.assertEqual(args.status, ["accepted"])
        self.assertEqual(args.user, "otheruser")
