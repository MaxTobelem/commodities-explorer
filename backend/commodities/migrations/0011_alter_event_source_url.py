from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commodities', '0010_alter_event_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='source_url',
            field=models.TextField(blank=True),
        ),
    ]
