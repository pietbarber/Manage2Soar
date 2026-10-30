from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("billing", "0010_remits_only_guest_remittance")]

    operations = [
        migrations.AlterModelOptions(
            name="billingperiod",
            options={
                "ordering": ("-year", "-month"),
                "permissions": (("can_manage_billing", "Can manage member billing"),),
            },
        ),
    ]
