# Adds created_at to UserSettings (it now inherits from TimeStampedModel).
#
# The settings row may already exist, and a new NOT NULL column needs a value for it.
# default=timezone.now fills existing rows once ("created now", the best we know);
# preserve_default=False then removes that default again, because from now on
# auto_now_add sets the value.

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersettings',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
