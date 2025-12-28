from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_membershiprequest_status_and_audit_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="business_contact_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="organization",
            name="business_contact_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="organization",
            name="business_contact_phone",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="organization",
            name="pr_marketing_contact_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="organization",
            name="pr_marketing_contact_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="organization",
            name="pr_marketing_contact_phone",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="organization",
            name="technical_contact_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="organization",
            name="technical_contact_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="organization",
            name="technical_contact_phone",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="organization",
            name="membership_level",
            field=models.ForeignKey(
                blank=True,
                null=True,
                limit_choices_to={"isOrganization": True},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="organizations",
                to="core.membershiptype",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="website_logo",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="organization",
            name="additional_information",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RemoveField(
            model_name="organization",
            name="contact",
        ),
    ]
