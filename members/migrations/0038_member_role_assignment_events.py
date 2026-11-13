import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("members", "0037_qualification_permission_bundle")]

    operations = [
        migrations.CreateModel(
            name="MemberRoleAssignmentEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "member_id_snapshot",
                    models.PositiveBigIntegerField(),
                ),
                ("member_username", models.CharField(max_length=150)),
                (
                    "group_id_snapshot",
                    models.PositiveBigIntegerField(),
                ),
                ("group_name", models.CharField(max_length=150)),
                ("role_key", models.CharField(blank=True, max_length=100)),
                (
                    "action",
                    models.CharField(
                        choices=[("grant", "Grant"), ("revoke", "Revoke")],
                        max_length=10,
                    ),
                ),
                ("source", models.CharField(max_length=20)),
                ("source_key", models.CharField(max_length=100)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "actor_id_snapshot",
                    models.PositiveBigIntegerField(blank=True, null=True),
                ),
                ("actor_username", models.CharField(blank=True, max_length=150)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_assignment_events_made",
                        to="members.member",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_assignment_events",
                        to="auth.group",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_assignment_events",
                        to="members.member",
                    ),
                ),
            ],
            options={
                "ordering": ("timestamp", "pk"),
                "default_permissions": (),
            },
        ),
    ]
