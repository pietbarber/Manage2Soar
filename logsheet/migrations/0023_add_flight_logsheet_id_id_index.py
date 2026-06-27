# Generated manually for stats export/admin performance on large historical datasets.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logsheet", "0022_flight_instruction_fee_actual"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="flight",
            index=models.Index(
                fields=["logsheet", "id"],
                name="logsheet_fl_logshee_25df4a_idx",
            ),
        ),
    ]
