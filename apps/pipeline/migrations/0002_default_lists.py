"""Start every agency with the usual lead sources and lost reasons."""

from django.db import migrations

SOURCES = ["Instagram", "Referral", "Paid Ads", "Cold Outreach", "Hot Outreach"]
REASONS = ["Too expensive", "No response", "Went with a competitor", "Not a fit", "Timing", "Other"]


def add_defaults(apps, schema_editor):
    LeadSource = apps.get_model("pipeline", "LeadSource")
    LostReason = apps.get_model("pipeline", "LostReason")
    for order, name in enumerate(SOURCES):
        LeadSource.objects.get_or_create(name=name, defaults={"order": order})
    for order, name in enumerate(REASONS):
        LostReason.objects.get_or_create(name=name, defaults={"order": order})


class Migration(migrations.Migration):
    dependencies = [("pipeline", "0001_initial")]
    operations = [migrations.RunPython(add_defaults, migrations.RunPython.noop)]
