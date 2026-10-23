"""Keep single-host systemd jobs in sync with the active GKE CronJobs."""

import re
from pathlib import Path

import yaml
from jinja2 import Template

ANSIBLE = Path(__file__).resolve().parents[1]
ROLE = ANSIBLE / "roles" / "m2s-app"

CRON_TO_CALENDAR = {
    "0 3 * * *": "*-*-* 03:00:00 UTC",
    "0 8 * * *": "*-*-* 08:00:00 UTC",
    "*/10 * * * *": "*-*-* *:00/10:00 UTC",
    "0 6 * * *": "*-*-* 06:00:00 UTC",
    "*/15 * * * *": "*-*-* *:00/15:00 UTC",
    "0 10 * * 1": "Mon *-*-* 10:00:00 UTC",
    "0 7 1 * *": "*-*-01 07:00:00 UTC",
}


def test_single_host_matches_active_gke_jobs():
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text())
    jobs = defaults["m2s_scheduled_jobs"]
    single_host = {job.get("command", job["name"]): job for job in jobs}
    assert len(single_host) == len(
        jobs
    ), "Every scheduled service needs a unique command"
    assert len({job["name"] for job in jobs}) == len(jobs)

    manifest = (
        ANSIBLE / "roles" / "gke-deploy" / "templates" / "k8s-cronjobs.yml.j2"
    ).read_text()
    gke = {}
    for section in manifest.split("\n---"):
        if not re.search(r"(?m)^kind: CronJob$", section):
            continue  # Disabled/commented-out jobs are not deployed.
        schedule = re.search(r'(?m)^  schedule: "([^"]+)"', section)
        assert "- manage.py" in section
        command = re.search(r"(?m)^\s+- (\w+)$", section.split("- manage.py", 1)[1])
        assert schedule and command
        gke[command[1]] = (schedule[1], section)

    assert set(single_host) == set(gke)

    service_template = Template(
        (ROLE / "templates" / "scheduled-job.service.j2").read_text()
    )
    timer_template = Template(
        (ROLE / "templates" / "scheduled-job.timer.j2").read_text()
    )
    for command, job in single_host.items():
        schedule, section = gke[command]
        assert job["calendar"] == CRON_TO_CALENDAR[schedule]
        deadline = re.search(r"activeDeadlineSeconds: (\d+)", section)
        assert deadline and job["timeout"] == int(deadline[1])
        if job.get("arguments"):
            assert f"- {job['arguments']}" in section

        context = dict(
            item=job,
            m2s_app_user="m2s",
            m2s_app_group="m2s",
            m2s_app_home="/opt/m2s",
            m2s_venv_path="/opt/m2s/venv",
        )
        service = service_template.render(**context)
        timer = timer_template.render(**context)
        assert f"ExecStart=/opt/m2s/venv/bin/python manage.py {command}" in service
        assert "EnvironmentFile=/opt/m2s/app/.env" in service
        assert f"TimeoutStartSec={job['timeout']}s" in service
        assert f"OnCalendar={job['calendar']}" in timer
        assert f"Unit=m2s-{job['name']}.service" in timer
        assert "Persistent=true" in timer
