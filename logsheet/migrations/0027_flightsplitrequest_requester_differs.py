from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("logsheet", "0026_flightsplitrequest_expiry")]

    operations = [
        migrations.AddConstraint(
            model_name="flightsplitrequest",
            constraint=models.CheckConstraint(
                condition=~models.Q(requester=models.F("requested_member")),
                name="split_request_requester_differs_from_requested_member",
            ),
        ),
    ]
