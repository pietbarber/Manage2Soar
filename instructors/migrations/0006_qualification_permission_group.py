from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("instructors", "0005_fix_legacy_score_5_to_needs_attention"),
        ("members", "0037_qualification_permission_bundle"),
    ]

    operations = [
        migrations.AddField(
            model_name="clubqualificationtype",
            name="permission_group",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optional opted-in Group whose explicit custom action permissions "
                    "apply while qualified; standard add/change/delete/view permissions "
                    "are not allowed."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="qualification_types",
                to="auth.group",
            ),
        ),
    ]
