import ast
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


def test_rendered_single_host_settings_protect_social_auth_user_fields():
    template_dir = Path(__file__).parents[1] / "templates"
    template = Environment(
        loader=FileSystemLoader(template_dir), autoescape=select_autoescape()
    ).get_template("settings_single_host.py.j2")
    rendered_settings = template.render(
        m2s_import_export_tmp_dir="/var/tmp/manage2soar/import-export"
    )
    settings_tree = ast.parse(rendered_settings)
    protected_fields_assignment = next(
        node
        for node in settings_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "SOCIAL_AUTH_PROTECTED_USER_FIELDS"
            for target in node.targets
        )
    )

    assert ast.literal_eval(protected_fields_assignment.value) == [
        "first_name",
        "last_name",
        "email",
    ]


def test_rendered_axes_cleanup_timer_and_service():
    """The single-host role ships an hourly django-axes cleanup timer +
    oneshot service that run the cleanup command as the app user through the
    ``manage.sh`` wrapper (issue #1110).  Verify the rendered units are
    coherent: the timer points at the service, the service runs the command,
    and both run as the unprivileged application user.
    """
    template_dir = Path(__file__).parents[1] / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir), autoescape=select_autoescape()
    )
    ctx = {
        "m2s_app_home": "/opt/m2s",
        "m2s_venv_path": "/opt/m2s/venv",
        "m2s_app_user": "m2s",
        "m2s_app_group": "m2s",
        "m2s_log_dir": "/var/log/m2s",
    }

    timer = env.get_template("m2s-cleanup-login-attempts.timer.j2").render(**ctx)
    service = env.get_template("m2s-cleanup-login-attempts.service.j2").render(**ctx)

    # Timer targets the oneshot service and is enabled on boot.
    assert "Unit=m2s-cleanup-login-attempts.service" in timer
    # Hourly schedule mirroring the K8s CronJob (minute 0 of every hour).
    assert "OnCalendar=*:00" in timer
    assert "WantedBy=timers.target" in timer

    # Service runs the cleanup command as the app user via manage.sh.
    assert "User=m2s" in service
    assert "Type=oneshot" in service
    assert "/opt/m2s/manage.sh cleanup_login_attempts --verbosity=1" in service
    assert "WorkingDirectory=/opt/m2s/app" in service
