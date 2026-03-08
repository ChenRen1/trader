from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trader", "0008_dailymarketreport"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="position_ratio",
            field=models.DecimalField(decimal_places=8, default=0, max_digits=12, verbose_name="持仓占比"),
        ),
    ]
