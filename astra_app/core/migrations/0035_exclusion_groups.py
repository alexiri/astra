from __future__ import annotations

import uuid

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0034_election_and_candidate_urls_and_candidate_nominated_by"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExclusionGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                (
                    "max_elected",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Maximum number of candidates from this group that may be elected.",
                        validators=[MinValueValidator(1)],
                    ),
                ),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "election",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="exclusion_groups",
                        to="core.election",
                    ),
                ),
            ],
            options={
                "ordering": ("election", "name", "id"),
            },
        ),
        migrations.CreateModel(
            name="ExclusionGroupCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "candidate",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="candidate_groups",
                        to="core.candidate",
                    ),
                ),
                (
                    "exclusion_group",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="group_candidates",
                        to="core.exclusiongroup",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="exclusiongroup",
            name="candidates",
            field=models.ManyToManyField(
                related_name="exclusion_groups",
                through="core.ExclusionGroupCandidate",
                to="core.candidate",
            ),
        ),
        migrations.AddConstraint(
            model_name="exclusiongroup",
            constraint=models.UniqueConstraint(
                fields=("election", "name"),
                name="uniq_exclusiongroup_election_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="exclusiongroupcandidate",
            constraint=models.UniqueConstraint(
                fields=("exclusion_group", "candidate"),
                name="uniq_exclusiongroupcandidate_group_candidate",
            ),
        ),
    ]
