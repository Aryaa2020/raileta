from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('raileta_api','0010_journeyevent_context')]
    operations = [migrations.CreateModel(name='SimulationSession',fields=[('name',models.CharField(max_length=50,primary_key=True,serialize=False)),('scenario_start',models.DateTimeField()),('wall_start',models.DateTimeField(default=django.utils.timezone.now)),('speed',models.FloatField(default=10)),('last_tick',models.DateTimeField(null=True))])]
