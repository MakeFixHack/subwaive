# Generated by Django 5.1.7 on 2025-03-27 23:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subwaive', '0008_alter_permission_options_event_recurrence_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='docusealsubmission',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
