"""Environment classification shared by every settings module.

Settings modules must not infer execution mode from unrelated configuration.
In particular, a production settings-module name that merely contains the
letters ``test`` (for example ``manage2soar.latest_settings``) must not be
treated as a test run.
"""

import os
import re
import sys
from pathlib import Path

_TEST_TOKENS = {"test", "tests", "testing"}


def is_test_settings_module(module_name):
    """Return True only for a settings module whose *name tokens* say test."""
    tokens = re.split(r"[^a-z0-9]+", (module_name or "").lower())
    return any(token in _TEST_TOKENS for token in tokens)


def is_testing(*, settings_module=None, argv=None, modules=None):
    """Detect a test run without changing any other environment behaviour.

    Only the runner/subcommand position counts.  Treating every argument named
    ``test`` as a runner makes ``manage.py loaddata test`` look like a test run,
    which would bypass production-only validation and weaken cookie security.
    """
    module_name = (
        os.getenv("DJANGO_SETTINGS_MODULE", "")
        if settings_module is None
        else settings_module
    )
    arguments = sys.argv if argv is None else argv
    loaded_modules = sys.modules if modules is None else modules

    if os.getenv("DJANGO_TESTING", "").lower() in {"true", "1", "yes"}:
        return True
    if is_test_settings_module(module_name):
        return True
    # ``python -m pytest`` keeps its entry point out of ``sys.argv[0]``.
    if "pytest" in loaded_modules:
        return True

    if not arguments:
        return False
    runner = Path(arguments[0]).name
    if runner in {"pytest", "py.test"}:
        return True
    return (
        len(arguments) > 1
        and runner in {"manage.py", "django-admin", "django-admin.py"}
        and arguments[1] == "test"
    )
