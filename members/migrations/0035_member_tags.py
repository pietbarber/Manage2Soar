from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0034_role_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemberTag",
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
                    "key",
                    models.CharField(
                        help_text="Stable identifier for this tag; changing it is discouraged.",
                        max_length=100,
                        unique=True,
                    ),
                ),
                ("display_label", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("sort_order", "display_label", "pk"),
                "default_permissions": (),
            },
        ),
        migrations.CreateModel(
            name="MemberTagAssignment",
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
                    "member",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="tag_assignments",
                        to="members.member",
                    ),
                ),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="assignments",
                        to="members.membertag",
                    ),
                ),
            ],
            options={
                "default_permissions": (),
                "ordering": ("member__last_name", "member__first_name", "pk"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tag", "member"),
                        name="unique_member_tag_assignment",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="membertag",
            name="members",
            field=models.ManyToManyField(
                related_name="member_tags",
                through="members.MemberTagAssignment",
                to="members.member",
            ),
        ),
    ]
