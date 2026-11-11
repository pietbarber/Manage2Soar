"""Regression tests for django-axes retention and its deployment schedules."""

from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.core.management import call_command
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
K8S_TEMPLATE = "infrastructure/ansible/roles/gke-deploy/templates/k8s-cronjobs.yml.j2"
SYSTEMD_TEMPLATES = "infrastructure/ansible/roles/m2s-app/templates"
MODELS = (AccessAttempt, AccessFailureLog, AccessLog)
FROZEN_NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


def _run_cleanup(*args):
    output = StringIO()
    with patch(
        "utils.management.commands.cleanup_login_attempts.timezone.now",
        return_value=FROZEN_NOW,
    ):
        call_command("cleanup_login_attempts", "--force", *args, stdout=output)
    return output.getvalue()


@pytest.mark.django_db
def test_cleanup_with_empty_axes_tables():
    for model in MODELS:
        assert not model.objects.exists()

    dry_run = _run_cleanup("--dry-run")
    assert (
        "Would delete 0 AccessAttempt, 0 AccessFailureLog, and 0 AccessLog" in dry_run
    )
    actual = _run_cleanup()
    assert "'AccessAttempt': 0" in actual
    assert "'AccessFailureLog': 0" in actual
    assert "'AccessLog': 0" in actual
    for model in MODELS:
        assert not model.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("dry_run", [True, False])
def test_exact_24_hour_cutoff_for_all_axes_tables(dry_run):
    cutoff = FROZEN_NOW - timedelta(hours=24)
    rows = {}
    for model in MODELS:
        rows[model] = {}
        for label, attempt_time in (
            ("old", cutoff - timedelta(microseconds=1)),
            ("boundary", cutoff),
            ("recent", cutoff + timedelta(microseconds=1)),
        ):
            fields = {"failures_since_start": 1} if model is AccessAttempt else {}
            row = model.objects.create(username=f"{model.__name__}-{label}", **fields)
            # Axes uses auto_now_add, so set the timestamps after insertion.
            model.objects.filter(pk=row.pk).update(attempt_time=attempt_time)
            rows[model][label] = row.pk

    output = _run_cleanup("--dry-run") if dry_run else _run_cleanup()
    if dry_run:
        assert (
            "Would delete 1 AccessAttempt, 1 AccessFailureLog, and 1 AccessLog"
            in output
        )

    for model, labelled in rows.items():
        remaining = set(
            model.objects.filter(pk__in=labelled.values()).values_list("pk", flat=True)
        )
        expected = (
            set(labelled.values())
            if dry_run
            else {labelled["boundary"], labelled["recent"]}
        )
        assert remaining == expected, model.__name__


def _cronjob(documents, name):
    matches = [
        doc for doc in documents if doc and doc.get("metadata", {}).get("name") == name
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_cleanup_cronjob(job, secret_name):
    assert job["kind"] == "CronJob"
    spec = job["spec"]
    assert spec["schedule"] == "0 * * * *"
    assert spec["timeZone"] == "UTC"
    assert spec["concurrencyPolicy"] == "Forbid"
    template = spec["jobTemplate"]["spec"]
    assert template["activeDeadlineSeconds"] == 300
    container = template["template"]["spec"]["containers"][0]
    assert container["command"] == [
        "python",
        "manage.py",
        "cleanup_login_attempts",
        "--verbosity=1",
    ]
    assert container["envFrom"] == [{"secretRef": {"name": secret_name}}]


def test_standalone_kubernetes_cleanup_schedule():
    documents = yaml.safe_load_all((ROOT / "k8s-cronjobs.yaml").read_text())
    _assert_cleanup_cronjob(
        _cronjob(documents, "cleanup-login-attempts"), "manage2soar-env"
    )


@pytest.mark.parametrize("multi_tenant", [False, True])
def test_rendered_ansible_kubernetes_cleanup_schedule(multi_tenant):
    environment = Environment(
        loader=FileSystemLoader(ROOT), undefined=StrictUndefined, autoescape=False
    )
    # Ansible's bool filter is used for the suspend flag in every CronJob.
    environment.filters["bool"] = bool
    # Jinja evaluates default() arguments eagerly; avoid the pipe/date lookup.
    environment.globals["lookup"] = lambda *_args: "2026-04-01T12:00:00Z"
    rendered = environment.get_template(K8S_TEMPLATE).render(
        ansible_date_time={"iso8601": "2026-04-01T12:00:00Z"},
        gke_club_prefix="testclub",
        gke_deployment_name="test-app",
        gke_namespace="test-ns",
        gke_multi_tenant=multi_tenant,
        gke_cronjobs_suspended=False,
        gke_image_name="example/app",
        gke_computed_image_tag="test",
        gke_secret_name="test-env",
        gke_gcp_credentials_path="/app/gcp-credentials.json",
        gke_gcp_credentials_filename="gcp-credentials.json",
        gke_gcp_sa_secret_name="gcp-sa-key",
    )
    job = _cronjob(yaml.safe_load_all(rendered), "test-app-cleanup-login-attempts")
    assert job["metadata"]["namespace"] == "test-ns"
    assert job["metadata"]["labels"].get("tenant") == (
        "testclub" if multi_tenant else None
    )
    assert job["spec"]["suspend"] is False
    _assert_cleanup_cronjob(job, "test-env")


def _render_systemd(name):
    environment = Environment(
        loader=FileSystemLoader(ROOT / SYSTEMD_TEMPLATES),
        undefined=StrictUndefined,
        autoescape=False,
    )
    rendered = environment.get_template(name).render(
        m2s_app_user="manage2soar",
        m2s_app_group="manage2soar",
        m2s_app_home="/srv/manage2soar",
        m2s_venv_path="/srv/manage2soar/venv",
    )
    config = ConfigParser(interpolation=None)
    config.read_string(rendered)
    return config


def test_rendered_systemd_cleanup_timer_and_service():
    timer = _render_systemd("m2s-cleanup-login-attempts.timer.j2")
    assert timer["Timer"]["OnCalendar"] == "*:00"
    assert timer["Timer"].getboolean("Persistent") is True
    assert timer["Timer"]["Unit"] == "m2s-cleanup-login-attempts.service"

    service = _render_systemd("m2s-cleanup-login-attempts.service.j2")
    assert service["Service"]["Type"] == "oneshot"
    assert service["Service"]["User"] == "manage2soar"
    assert service["Service"]["Group"] == "manage2soar"
    assert service["Service"]["WorkingDirectory"] == "/srv/manage2soar/app"
    assert service["Service"]["EnvironmentFile"] == "/srv/manage2soar/app/.env"
    assert service["Service"]["ExecStart"] == (
        "/srv/manage2soar/venv/bin/python /srv/manage2soar/app/manage.py "
        "cleanup_login_attempts --verbosity=1"
    )
    assert service["Service"]["TimeoutStartSec"] == "300"
