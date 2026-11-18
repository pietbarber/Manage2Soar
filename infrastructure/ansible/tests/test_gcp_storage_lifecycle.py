"""Guard the lifecycle-file update against dropping unmanaged bucket rules."""

from pathlib import Path

import yaml
from jinja2 import Template

PLAYBOOK = Path(__file__).resolve().parents[1] / "playbooks/gcp-storage.yml"


def test_lifecycle_reconciliation_refuses_unmanaged_rules_before_replacement():
    tasks = yaml.safe_load(PLAYBOOK.read_text())[0]["tasks"]
    guard_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Reject unmanaged import/export lifecycle rules"
    )
    update_index = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Apply import/export object expiration lifecycle policy"
    )
    guard = tasks[guard_index]["ansible.builtin.assert"]

    assert guard_index < update_index
    assert "reconcile" in guard["fail_msg"]

    check = Template("{{ " + guard["that"][0] + " }}")
    managed = [
        {"action": {"type": "Delete"}, "condition": {"age": 1}},
        {"action": {"type": "Delete"}, "condition": {"age": 7}},
    ]
    assert (
        check.render(item=managed[0], import_export_managed_lifecycle_rules=managed)
        == "True"
    )
    assert (
        check.render(
            item={"action": "SetStorageClass"},
            import_export_managed_lifecycle_rules=managed,
        )
        == "False"
    )
