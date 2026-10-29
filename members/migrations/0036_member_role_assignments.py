from django.db import migrations, models
import django.db.models.deletion


ROLE_GROUPS = {
    "Rostermeisters": "rostermeister",
    "Instructor Admins": "instructor",
    "Member Managers": "member_manager",
    "Webmasters": "webmaster",
    "Secretary": "secretary",
    "Treasurer": "treasurer",
}


def backfill_role_assignments(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Member = apps.get_model("members", "Member")
    Assignment = apps.get_model("members", "MemberRoleAssignment")

    for member in Member.objects.using(db_alias).all().iterator():
        for group in member.groups.using(db_alias).all():
            source_key = ROLE_GROUPS.get(group.name)
            if source_key and getattr(member, source_key, False):
                source = "legacy"
            else:
                source = "manual"
                source_key = "migration"
            Assignment.objects.using(db_alias).create(
                member_id=member.pk,
                group_id=group.pk,
                source=source,
                source_key=source_key,
            )


class Migration(migrations.Migration):
    dependencies = [("members", "0035_member_tags")]

    operations = [
        migrations.CreateModel(
            name="MemberRoleAssignment",
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
                ("source", models.CharField(max_length=20, choices=[("manual", "Manual"), ("status", "Status"), ("legacy", "Legacy role flag")])),
                ("source_key", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="role_assignments_made",
                        to="members.member",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="member_role_assignments",
                        to="auth.group",
                    ),
                ),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_assignments",
                        to="members.member",
                    ),
                ),
            ],
            options={"default_permissions": ()},
        ),
        migrations.AddConstraint(
            model_name="memberroleassignment",
            constraint=models.UniqueConstraint(
                fields=("member", "group", "source", "source_key"),
                name="unique_member_role_assignment_provenance",
            ),
        ),
        migrations.RunPython(backfill_role_assignments, migrations.RunPython.noop),
    ]
