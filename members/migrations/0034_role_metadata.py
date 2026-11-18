from django.db import migrations, models

# These six built-in roles correspond to the existing MailingListCriterion
# values: instructor, webmaster, member_manager, rostermeister, secretary,
# and treasurer.  They are eligible here so existing role-based audiences can
# be represented by stable role keys in a later slice.
CANONICAL_ROLE_METADATA = (
    {
        "group_name": "Instructor Admins",
        "key": "instructor_admins",
        "description": "Manage instructor training and knowledge tests.",
        "sort_order": 10,
    },
    {
        "group_name": "Webmasters",
        "key": "webmasters",
        "description": "Manage club website content and configuration.",
        "sort_order": 20,
    },
    {
        "group_name": "Member Managers",
        "key": "member_managers",
        "description": "Manage member records and membership workflows.",
        "sort_order": 30,
    },
    {
        "group_name": "Rostermeisters",
        "key": "rostermeisters",
        "description": "Manage duty-roster scheduling.",
        "sort_order": 40,
    },
    {
        "group_name": "Secretary",
        "key": "secretary",
        "description": "Club secretary role.",
        "sort_order": 50,
    },
    {
        "group_name": "Treasurer",
        "key": "treasurer",
        "description": "Club treasurer role.",
        "sort_order": 60,
    },
)


def _get_canonical_groups(Group, db_alias):
    canonical_groups = {}
    for role in CANONICAL_ROLE_METADATA:
        matches = list(
            Group.objects.using(db_alias)
            .filter(name=role["group_name"])
            .order_by("pk")
        )
        if not matches:
            raise RuntimeError(
                "RoleMetadata migration cannot continue: canonical Group "
                f"{role['group_name']!r} is missing. Restore or create the "
                "canonical Group before re-running migration 0034."
            )
        if len(matches) > 1:
            ids = ", ".join(str(group.pk) for group in matches)
            raise RuntimeError(
                "RoleMetadata migration cannot continue: canonical Group "
                f"{role['group_name']!r} has duplicate rows (pks: {ids}). "
                "Resolve the duplicate data before re-running migration 0034."
            )
        canonical_groups[role["group_name"]] = matches[0]
    return canonical_groups


def seed_canonical_role_metadata(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    RoleMetadata = apps.get_model("members", "RoleMetadata")
    canonical_groups = _get_canonical_groups(Group, db_alias)

    for role in CANONICAL_ROLE_METADATA:
        group = canonical_groups[role["group_name"]]

        # Do not replace metadata that may have been created before this
        # migration.  In particular, preserve any edited display values.
        existing_metadata = (
            RoleMetadata.objects.using(db_alias)
            .filter(group_id=group.pk)
            .first()
        )
        if existing_metadata is not None:
            if existing_metadata.key != role["key"]:
                raise RuntimeError(
                    "RoleMetadata migration cannot continue: canonical Group "
                    f"{role['group_name']!r} already has metadata key "
                    f"{existing_metadata.key!r}, expected {role['key']!r}."
                )
            continue

        # A pre-existing key owned by another group is left untouched, but the
        # migration must fail rather than silently omit this canonical role.
        key_collision = (
            RoleMetadata.objects.using(db_alias).filter(key=role["key"]).first()
        )
        if key_collision is not None:
            raise RuntimeError(
                "RoleMetadata migration cannot continue: stable key "
                f"{role['key']!r} is already used by metadata pk "
                f"{key_collision.pk}. Resolve the collision before re-running "
                "migration 0034."
            )

        RoleMetadata.objects.using(db_alias).create(
            group_id=group.pk,
            key=role["key"],
            display_name=role["group_name"],
            description=role["description"],
            is_builtin=True,
            is_protected=True,
            is_system_managed=True,
            is_assignable=True,
            mailing_list_eligible=True,
            sort_order=role["sort_order"],
        )


class Migration(migrations.Migration):
    dependencies = [("members", "0033_member_manager_emergency_contact_permissions")]

    operations = [
        migrations.CreateModel(
            name="RoleMetadata",
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
                ("key", models.CharField(max_length=100, unique=True)),
                ("display_name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True)),
                ("is_builtin", models.BooleanField(default=False)),
                ("is_protected", models.BooleanField(default=False)),
                ("is_system_managed", models.BooleanField(default=False)),
                ("is_assignable", models.BooleanField(default=True)),
                ("mailing_list_eligible", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="role_metadata",
                        to="auth.group",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "display_name", "pk")},
        ),
        migrations.RunPython(
            seed_canonical_role_metadata,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
