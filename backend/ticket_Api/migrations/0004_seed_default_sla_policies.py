from django.db import migrations


def create_default_sla_policies(apps, schema_editor):

    SLAPolicy = apps.get_model("ticket_Api", "SLAPolicy")
    database = schema_editor.connection.alias

    policies = [
        ("CRITICAL", 15, 240),
        ("HIGH", 60, 480),
        ("MEDIUM", 240, 1440),
        ("LOW", 480, 2880),
    ]

    for priority, response_time, resolution_time in policies:

        SLAPolicy.objects.using(database).get_or_create(
            priority=priority,
            defaults={
                "response_time_minutes": response_time,
                "resolution_time_minutes": resolution_time,
                "is_active": True,
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ("ticket_Api", "0003_slapolicy_ticketsla_ticketescalation"),
    ]

    operations = [
        migrations.RunPython(
            create_default_sla_policies,
            migrations.RunPython.noop
        ),
    ]
