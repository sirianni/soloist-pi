"""Smoke tests for the initial command-line scaffold."""

import unittest

from soloist_pi.cli import build_parser


class CommandLineTests(unittest.TestCase):
    def test_planned_commands_are_registered(self) -> None:
        parser = build_parser()

        for command in ("run", "update", "ctl"):
            with self.subTest(command=command):
                args = parser.parse_args([command])
                self.assertEqual(args.command, command)


if __name__ == "__main__":
    unittest.main()
