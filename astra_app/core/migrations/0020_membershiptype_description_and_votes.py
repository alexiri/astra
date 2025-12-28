from __future__ import annotations

from django.db import migrations, models


def _populate_membershiptype_description_and_votes(apps, schema_editor) -> None:
    MembershipType = apps.get_model("core", "MembershipType")

    sponsor_descriptions: dict[str, str] = {
        "platinum": "Platinum Sponsor Member (Annual dues: $100,000 USD)",
        "gold": "Gold Sponsor Member (Annual dues: $20,000 USD)",
        "ruby": "Ruby Sponsor Member (Annual dues: $5,000 USD)",
        "silver": "Silver Sponsor Member (Annual dues: $2,500 USD)",
    }

    votes_by_code: dict[str, int] = {
        "individual": 1,
        "mirror": 1,
        "platinum": 50,
        "gold": 15,
        "ruby": 5,
        "silver": 5,
    }

    # Update existing rows only; do not create new membership types.
    for code, votes in votes_by_code.items():
        MembershipType.objects.filter(code=code).update(votes=votes)

    for code, description in sponsor_descriptions.items():
        MembershipType.objects.filter(code=code).update(description=description)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_organization_sponsorship_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="membershiptype",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="membershiptype",
            name="votes",
            field=models.PositiveIntegerField(blank=True, default=0),
        ),
        migrations.RunPython(
            _populate_membershiptype_description_and_votes,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
