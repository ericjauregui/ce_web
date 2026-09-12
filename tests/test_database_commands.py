from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from scripts import database


class DatabaseCommandTests(unittest.TestCase):
    def test_failed_migration_exits_without_exposing_driver_details(self) -> None:
        output = io.StringIO()
        with (
            patch.object(database, "database_url_from_env", return_value="postgresql://unused"),
            patch.object(database.command, "upgrade", side_effect=RuntimeError("sensitive-driver-detail")),
            redirect_stderr(output),
            redirect_stdout(output),
        ):
            status = database.main(["migrate"])
        self.assertEqual(status, 1)
        self.assertIn("Database operation failed", output.getvalue())
        self.assertNotIn("sensitive-driver-detail", output.getvalue())
        self.assertNotIn("postgresql://", output.getvalue())

    def test_missing_configuration_does_not_claim_success(self) -> None:
        output = io.StringIO()
        with (
            patch.object(database, "database_url_from_env", side_effect=RuntimeError("missing")),
            redirect_stderr(output),
            redirect_stdout(output),
        ):
            status = database.main(["check"])
        self.assertEqual(status, 1)
        self.assertNotIn("connection OK", output.getvalue())
