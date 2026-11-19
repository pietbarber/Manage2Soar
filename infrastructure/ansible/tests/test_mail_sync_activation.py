"""Keep mail configuration activation behind a successful initial sync."""

from pathlib import Path

import yaml

ANSIBLE = Path(__file__).resolve().parents[1]
SYNC_TASKS = (
    ANSIBLE / "roles" / "m2s-mail-sync" / "tasks" / "main.yml"
)


def test_mail_handlers_are_activated_only_after_successful_initial_sync():
    tasks = yaml.safe_load(SYNC_TASKS.read_text())
    sync = next(task for task in tasks if task["name"] == "Run initial sync")
    activate = next(
        task
        for task in tasks
        if task["name"] == "Activate mail configuration after successful sync"
    )

    assert sync["register"] == "m2s_initial_sync"
    assert sync.get("ignore_errors") is not True
    assert sync.get("failed_when") is not False
    assert activate["ansible.builtin.meta"] == "flush_handlers"
    assert activate["when"] == "m2s_initial_sync.rc == 0"
    assert "always" not in activate.get("tags", [])
