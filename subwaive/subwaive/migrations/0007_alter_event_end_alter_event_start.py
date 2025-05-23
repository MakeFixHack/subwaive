# Generated by Django 5.1.7 on 2025-03-23 17:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subwaive', '0006_personevent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='end',
            field=models.DateTimeField(help_text='When does the event finish?'),
        ),
        migrations.AlterField(
            model_name='event',
            name='start',
            field=models.DateTimeField(help_text='When does the event begin?'),
        ),
    ]
