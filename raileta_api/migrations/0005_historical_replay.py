from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("raileta_api", "0004_feedsnapshot_content_bytes_and_more")]
    operations = [
        migrations.CreateModel(
            name="HistoricalReplaySession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=160, unique=True)),
                ("model_version", models.CharField(max_length=80)),
                ("generation", models.PositiveIntegerField(default=1)),
                ("next_index", models.PositiveIntegerField(default=0)),
                ("next_due_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_replayed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="HistoricalRunPrediction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("generation", models.PositiveIntegerField()),
                ("record_id", models.CharField(max_length=100)),
                ("train_number", models.CharField(max_length=20)),
                ("model_version", models.CharField(max_length=80)),
                ("original_record", models.JSONField()),
                ("prediction", models.JSONField()),
                ("replayed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="raileta_api.trainevent")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="raileta_api.historicalreplaysession")),
            ],
            options={
                "indexes": [models.Index(fields=["session", "generation", "train_number"], name="historical_session_train_idx")],
                "constraints": [models.UniqueConstraint(fields=("session", "generation", "record_id"), name="unique_historical_run_generation")],
            },
        ),
    ]
