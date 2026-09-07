from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("raileta_api", "0002_alter_trainevent_received_at")]

    operations = [
        migrations.CreateModel(
            name="FeedSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=40)),
                ("endpoint", models.URLField(max_length=500)),
                ("fetched_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("http_status", models.PositiveIntegerField(default=200)),
                ("parser_version", models.CharField(default="public-v1", max_length=40)),
                ("payload", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True)),
            ],
            options={"indexes": [models.Index(fields=["source", "fetched_at"], name="raileta_api_source_f4dfc8_idx")]},
        ),
    ]
