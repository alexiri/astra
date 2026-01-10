from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0044_rename_mailmerge_permission_to_sendmail"),
    ]

    operations = [
        migrations.CreateModel(
            name="Note",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=255)),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("content", models.TextField(blank=True, null=True)),
                ("action", models.JSONField(blank=True, null=True)),
                (
                    "membership_request",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="notes", to="core.membershiprequest"),
                ),
            ],
            options={
                "ordering": ("timestamp", "pk"),
            },
        ),
        migrations.AddIndex(
            model_name="note",
            index=models.Index(fields=["membership_request", "timestamp"], name="note_req_at"),
        ),
        migrations.AddIndex(
            model_name="note",
            index=models.Index(fields=["membership_request", "username", "timestamp"], name="note_req_user_at"),
        ),
        migrations.AddConstraint(
            model_name="note",
            constraint=models.CheckConstraint(
                condition=Q(("content__isnull", False)) | Q(("action__isnull", False)),
                name="chk_note_content_or_action",
            ),
        ),
    ]
