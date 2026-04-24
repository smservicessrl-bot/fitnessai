from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0003_weekly_workout_frequency"),
    ]

    operations = [
        migrations.CreateModel(
            name="GymEquipment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "equipment",
                    models.CharField(
                        db_index=True,
                        max_length=100,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Edzőtermi eszköz",
                "verbose_name_plural": "Edzőtermi eszközök",
                "ordering": ["equipment"],
            },
        ),
    ]
