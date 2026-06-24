from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calculator', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='precisiontype',
            name='name',
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
