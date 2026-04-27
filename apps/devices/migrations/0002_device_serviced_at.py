from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='serviced_at',
            field=models.DateField(blank=True, null=True, verbose_name='Дата обслуживания'),
        ),
    ]
