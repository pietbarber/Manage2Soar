from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("instructors", "0007_qualification_permission_grant"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="groundinstruction",
            options={
                "ordering": ["-date"],
                "permissions": [
                    (
                        "can_manage_ground_instruction",
                        "Can manage ground instruction",
                    ),
                ],
            },
        ),
    ]
