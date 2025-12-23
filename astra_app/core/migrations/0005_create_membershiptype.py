from __future__ import annotations

from django.db import migrations, models


def seed_membership_types(apps, schema_editor) -> None:
    MembershipType = apps.get_model("core", "MembershipType")

    initial = [
        {
            "code": "individual",
            "name": "Individual",
            "isIndividual": True,
            "isOrganization": False,
            "sort_order": 10,
            "enabled": True,
        },
        {
            "code": "mirror",
            "name": "Mirror",
            "isIndividual": True,
            "isOrganization": True,
            "sort_order": 20,
            "enabled": True,
        },
        {
            "code": "platinum",
            "name": "Platinum Sponsor",
            "isIndividual": False,
            "isOrganization": True,
            "sort_order": 30,
            "enabled": True,
        },
        {
            "code": "gold",
            "name": "Gold Sponsor",
            "isIndividual": False,
            "isOrganization": True,
            "sort_order": 40,
            "enabled": True,
        },
        {
            "code": "silver",
            "name": "Silver Sponsor",
            "isIndividual": False,
            "isOrganization": True,
            "sort_order": 50,
            "enabled": True,
        },
        {
            "code": "ruby",
            "name": "Ruby Sponsor",
            "isIndividual": False,
            "isOrganization": True,
            "sort_order": 60,
            "enabled": True,
        },
    ]

    for row in initial:
        code = row.pop("code")
        MembershipType.objects.update_or_create(code=code, defaults=row)


def unseed_membership_types(apps, schema_editor) -> None:
    MembershipType = apps.get_model("core", "MembershipType")
    MembershipType.objects.filter(code__in=["individual", "mirror", "platinum", "gold", "silver", "ruby"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_create_ipauser_contenttype"),
    ]

    operations = [
        migrations.CreateModel(
            name="MembershipType",
            fields=[
                ("code", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("isIndividual", models.BooleanField(default=False)),
                ("isOrganization", models.BooleanField(default=False)),
                ("sort_order", models.IntegerField(default=0)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("sort_order", "code"),
            },
        ),
        migrations.RunPython(seed_membership_types, reverse_code=unseed_membership_types),
    ]
