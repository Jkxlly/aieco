from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('calculator', '0002_alter_precisiontype_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='promptemissions',
            name='input_tokens',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='promptemissions',
            name='output_tokens',
            field=models.IntegerField(default=0, help_text='Estimated; output dominates energy'),
        ),
        migrations.AddField(
            model_name='promptemissions',
            name='pue',
            field=models.FloatField(default=0, help_text='Data-centre overhead factor applied'),
        ),
        migrations.AddField(
            model_name='promptemissions',
            name='co2_grams_low',
            field=models.FloatField(default=0, help_text='Lower uncertainty bound'),
        ),
        migrations.AddField(
            model_name='promptemissions',
            name='co2_grams_high',
            field=models.FloatField(default=0, help_text='Upper uncertainty bound'),
        ),
        migrations.AlterField(
            model_name='promptemissions',
            name='token_count',
            field=models.IntegerField(default=0, help_text='Total tokens (input + output)'),
        ),
        migrations.AlterField(
            model_name='promptemissions',
            name='co2_grams',
            field=models.FloatField(default=0, help_text='Central estimate'),
        ),
    ]
