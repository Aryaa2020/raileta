"""Operator-friendly alias for the structured data-source collector."""
from .collect_public import Command


class Command(Command):
    help = "Poll the configured structured data adapter and persist events."
