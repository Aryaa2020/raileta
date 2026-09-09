from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('raileta_api', '0009_optional_section_metadata')]
    operations = [migrations.AddField(model_name='journeyevent', name='context', field=models.JSONField(default=dict, blank=True))]
