#!/usr/bin/env python
"""Django management entrypoint for the submission-aligned RailETA API."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_service.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
