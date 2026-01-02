from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


GENESIS_CHAIN_HASH = "0" * 64


BALLOT_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION core_ballot_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ballot rows are append-only (DELETE is not allowed)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS core_ballot_no_delete_trg ON core_ballot;
CREATE TRIGGER core_ballot_no_delete_trg
BEFORE DELETE ON core_ballot
FOR EACH ROW
EXECUTE FUNCTION core_ballot_no_delete();


CREATE OR REPLACE FUNCTION core_ballot_restrict_update() RETURNS trigger AS $$
BEGIN
    -- Append-only: forbid updates to any field other than superseded_by_id and is_counted.
    --
    -- Supersession validity (self-reference, forward-only, same election/credential, cycles)
    -- is enforced by the DEFERRABLE constraint trigger `core_ballot_validate_supersession_trg`.
    IF NEW.election_id IS DISTINCT FROM OLD.election_id
        OR NEW.credential_public_id IS DISTINCT FROM OLD.credential_public_id
        OR NEW.ranking IS DISTINCT FROM OLD.ranking
        OR NEW.weight IS DISTINCT FROM OLD.weight
        OR NEW.ballot_hash IS DISTINCT FROM OLD.ballot_hash
        OR NEW.previous_chain_hash IS DISTINCT FROM OLD.previous_chain_hash
        OR NEW.chain_hash IS DISTINCT FROM OLD.chain_hash
        OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'ballot rows are append-only (only superseded_by_id and is_counted may be updated)';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS core_ballot_restrict_update_trg ON core_ballot;
CREATE TRIGGER core_ballot_restrict_update_trg
BEFORE UPDATE ON core_ballot
FOR EACH ROW
EXECUTE FUNCTION core_ballot_restrict_update();


CREATE OR REPLACE FUNCTION core_ballot_validate_supersession() RETURNS trigger AS $$
DECLARE
    cur_superseded_by_id bigint;
    cur_election_id integer;
    cur_credential_public_id text;
    target_election_id integer;
    target_credential_public_id text;
    cycle_found integer;
BEGIN
    -- This is a DEFERRABLE constraint trigger. Re-read the current row state
    -- so temporary states within a transaction don't cause false failures.
    SELECT superseded_by_id, election_id, credential_public_id
      INTO cur_superseded_by_id, cur_election_id, cur_credential_public_id
      FROM core_ballot
     WHERE id = NEW.id;

    IF cur_superseded_by_id IS NULL THEN
        RETURN NULL;
    END IF;

    IF cur_superseded_by_id = NEW.id THEN
        RAISE EXCEPTION 'superseded_by cannot reference itself';
    END IF;

    IF cur_superseded_by_id <= NEW.id THEN
        RAISE EXCEPTION 'superseded_by must reference a later ballot';
    END IF;

    SELECT election_id, credential_public_id
      INTO target_election_id, target_credential_public_id
      FROM core_ballot
     WHERE id = cur_superseded_by_id;

    IF target_election_id IS NULL THEN
        RAISE EXCEPTION 'superseded_by ballot not found';
    END IF;

    IF target_election_id <> cur_election_id
        OR target_credential_public_id <> cur_credential_public_id THEN
        RAISE EXCEPTION 'superseded_by must reference a ballot with the same election and credential_public_id';
    END IF;

    WITH RECURSIVE next_ids(id) AS (
        SELECT cur_superseded_by_id
        UNION
        SELECT b.superseded_by_id
          FROM core_ballot b
          JOIN next_ids n ON b.id = n.id
         WHERE b.superseded_by_id IS NOT NULL
    )
    SELECT 1 INTO cycle_found FROM next_ids WHERE id = NEW.id LIMIT 1;

    IF cycle_found IS NOT NULL THEN
        RAISE EXCEPTION 'superseded_by would create a cycle';
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS core_ballot_validate_supersession_trg ON core_ballot;
CREATE CONSTRAINT TRIGGER core_ballot_validate_supersession_trg
AFTER INSERT OR UPDATE OF superseded_by_id ON core_ballot
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION core_ballot_validate_supersession();
"""


BALLOT_APPEND_ONLY_SQL_REVERSE = """
DROP TRIGGER IF EXISTS core_ballot_validate_supersession_trg ON core_ballot;

DROP TRIGGER IF EXISTS core_ballot_restrict_update_trg ON core_ballot;
DROP TRIGGER IF EXISTS core_ballot_no_delete_trg ON core_ballot;

DROP FUNCTION IF EXISTS core_ballot_validate_supersession();

DROP FUNCTION IF EXISTS core_ballot_restrict_update();
DROP FUNCTION IF EXISTS core_ballot_no_delete();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_add_election_email_config"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ballot",
            name="ballot_hash",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="ballot",
            name="previous_chain_hash",
            field=models.CharField(default=GENESIS_CHAIN_HASH, max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ballot",
            name="chain_hash",
            field=models.CharField(default=GENESIS_CHAIN_HASH, max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ballot",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="supersedes",
                to="core.ballot",
            ),
        ),
        migrations.AddField(
            model_name="ballot",
            name="is_counted",
            field=models.BooleanField(default=True),
        ),
        migrations.RemoveConstraint(
            model_name="ballot",
            name="uniq_ballot_election_credential",
        ),
        migrations.AddConstraint(
            model_name="ballot",
            constraint=models.UniqueConstraint(
                condition=Q(superseded_by__isnull=True),
                fields=("election", "credential_public_id"),
                name="uniq_ballot_final_election_credential",
            ),
        ),
        migrations.AddConstraint(
            model_name="ballot",
            constraint=models.UniqueConstraint(
                condition=Q(is_counted=True),
                fields=("election", "credential_public_id"),
                name="uniq_ballot_counted_election_credential",
            ),
        ),
        migrations.RunSQL(
            sql=BALLOT_APPEND_ONLY_SQL,
            reverse_sql=BALLOT_APPEND_ONLY_SQL_REVERSE,
        ),
    ]
