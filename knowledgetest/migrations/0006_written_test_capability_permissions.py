from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("knowledgetest", "0005_grant_instructor_admin_knowledgetest_permissions")]

    operations = [
        migrations.AlterModelOptions(
            name="writtentesttemplate",
            options={
                "permissions": [
                    (
                        "start_unassigned_written_test",
                        "Can start and submit an unassigned written test",
                    )
                ]
            },
        ),
        migrations.AlterModelOptions(
            name="writtentestattempt",
            options={
                "permissions": [
                    ("delete_any_written_test_attempt", "Can delete any written test attempt"),
                    ("view_recent_written_tests", "Can view recent written tests"),
                ]
            },
        ),
        migrations.AlterModelOptions(
            name="writtentestassignment",
            options={
                "permissions": [
                    (
                        "delete_any_pending_written_test_assignment",
                        "Can delete any pending written test assignment",
                    )
                ],
                "unique_together": {("template", "student")},
            },
        ),
    ]
