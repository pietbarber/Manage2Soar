from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("knowledgetest", "0008_create_and_grant_written_test_capabilities")
    ]

    operations = [
        migrations.AlterModelOptions(
            name="testpreset",
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name": "Test Preset",
                "verbose_name_plural": "Test Presets",
                "permissions": [
                    (
                        "can_manage_test_presets",
                        "Can add and change shared test presets",
                    ),
                    ("can_delete_test_presets", "Can delete shared test presets"),
                ],
            },
        )
    ]
