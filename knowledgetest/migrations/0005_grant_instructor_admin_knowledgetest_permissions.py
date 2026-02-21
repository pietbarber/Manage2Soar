"""
Data migration: grant missing knowledgetest permissions to "Instructor Admins"
group (Issue: instructors cannot access /admin/knowledgetest/testpreset/).

When TestPreset, WrittenTestTemplate, WrittenTestAttempt, and WrittenTestAnswer
were added to the knowledgetest app, the "Instructor Admins" group permissions
fixture was not updated.  Instructors ended up with Question / QuestionCategory
access only, blocking them from the TestPreset and WrittenTest* admin pages they
need to do their job.

Granted permissions:
  - testpreset           : add, change, delete, view  (instructors manage presets)
  - writtentesttemplate  : add, change, delete, view  (instructors manage templates)
  - writtentestattempt   : view only (read-only admin; student records)
  - writtentestanswer    : view only (read-only admin; student records)
  - writtentesttemplatequestion : add, change, delete, view (inline on template)
"""

from django.db import migrations

INSTRUCTOR_ADMIN_PERMISSIONS = [
    ("knowledgetest", "testpreset", "add_testpreset"),
    ("knowledgetest", "testpreset", "change_testpreset"),
    ("knowledgetest", "testpreset", "delete_testpreset"),
    ("knowledgetest", "testpreset", "view_testpreset"),
    ("knowledgetest", "writtentestanswer", "view_writtentestanswer"),
    ("knowledgetest", "writtentestattempt", "view_writtentestattempt"),
    ("knowledgetest", "writtentesttemplate", "add_writtentesttemplate"),
    ("knowledgetest", "writtentesttemplate", "change_writtentesttemplate"),
    ("knowledgetest", "writtentesttemplate", "delete_writtentesttemplate"),
    ("knowledgetest", "writtentesttemplate", "view_writtentesttemplate"),
    ("knowledgetest", "writtentesttemplatequestion", "add_writtentesttemplatequestion"),
    (
        "knowledgetest",
        "writtentesttemplatequestion",
        "change_writtentesttemplatequestion",
    ),
    (
        "knowledgetest",
        "writtentesttemplatequestion",
        "delete_writtentesttemplatequestion",
    ),
    (
        "knowledgetest",
        "writtentesttemplatequestion",
        "view_writtentesttemplatequestion",
    ),
]


def grant_instructor_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        group = Group.objects.using(db_alias).get(name="Instructor Admins")
    except Group.DoesNotExist:
        # Group hasn't been created yet (fresh install); members/0021 will create
        # it with all permissions during the migration run.
        return

    perms_to_add = []
    for app_label, model_name, codename in INSTRUCTOR_ADMIN_PERMISSIONS:
        try:
            ct = ContentType.objects.using(db_alias).get(
                app_label=app_label, model=model_name
            )
            perm = Permission.objects.using(db_alias).get(
                content_type=ct, codename=codename
            )
            perms_to_add.append(perm)
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            # Permission may not exist yet on very old schema versions; skip.
            pass

    if perms_to_add:
        group.permissions.db_manager(db_alias).add(*perms_to_add)


def revoke_instructor_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        group = Group.objects.using(db_alias).get(name="Instructor Admins")
    except Group.DoesNotExist:
        return

    perms_to_remove = []
    for app_label, model_name, codename in INSTRUCTOR_ADMIN_PERMISSIONS:
        try:
            ct = ContentType.objects.using(db_alias).get(
                app_label=app_label, model=model_name
            )
            perm = Permission.objects.using(db_alias).get(
                content_type=ct, codename=codename
            )
            perms_to_remove.append(perm)
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            pass

    if perms_to_remove:
        group.permissions.db_manager(db_alias).remove(*perms_to_remove)


class Migration(migrations.Migration):

    dependencies = [
        ("knowledgetest", "0004_populate_test_presets"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("members", "0021"),
    ]

    operations = [
        migrations.RunPython(
            grant_instructor_permissions,
            reverse_code=revoke_instructor_permissions,
        ),
    ]
