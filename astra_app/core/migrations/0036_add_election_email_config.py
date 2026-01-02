from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0035_exclusion_groups"),
        ("post_office", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="election",
            name="voting_email_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="post_office.emailtemplate",
            ),
        ),
        migrations.AddField(
            model_name="election",
            name="voting_email_subject",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="election",
            name="voting_email_html",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="election",
            name="voting_email_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
