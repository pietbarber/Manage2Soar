"""Add DC and APO/FPO/DPO to Member.state_code choices."""

from django.db import migrations, models

# Snapshot of US_STATE_CHOICES (including DC and military regions)
US_STATE_CHOICES_SNAPSHOT = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
    ("DC", "District of Columbia"),
    # Military APO regions (USPS special service)
    ("AA", "APO (Armed Forces Americas)"),
    ("AE", "APO (Armed Forces Europe)"),
    ("AP", "APO (Armed Forces Pacific)"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0026_alter_member_membership_status_visitingpilotvisit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="state_code",
            field=models.CharField(
                blank=True,
                choices=US_STATE_CHOICES_SNAPSHOT,
                max_length=2,
                null=True,
            ),
        ),
    ]
