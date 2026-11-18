from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("instructors", "0006_qualification_permission_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="QualificationPermissionGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.group")),
                ("permission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="auth.permission")),
            ],
        ),
        migrations.AddConstraint(
            model_name="qualificationpermissiongrant",
            constraint=models.UniqueConstraint(fields=("group", "permission"), name="unique_qualification_permission_grant"),
        ),
    ]
