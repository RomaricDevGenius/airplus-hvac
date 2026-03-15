from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "notif_type",
                    models.CharField(
                        choices=[
                            ("stock_alert", "Alerte stock"),
                            ("new_quote", "Nouveau devis"),
                        ],
                        max_length=20,
                        verbose_name="Type",
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="Titre")),
                ("message", models.TextField(verbose_name="Message")),
                (
                    "link",
                    models.CharField(blank=True, max_length=500, verbose_name="Lien"),
                ),
                (
                    "is_read",
                    models.BooleanField(default=False, verbose_name="Lu"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Notification",
                "verbose_name_plural": "Notifications",
                "db_table": "accounts_notification",
                "ordering": ["-created_at"],
            },
        ),
    ]
