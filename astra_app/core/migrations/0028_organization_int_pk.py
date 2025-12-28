from __future__ import annotations

from django.db import migrations, models


_ORG_INT_PK_SQL: list[str] = [
    """
    -- 1) Add an integer id column with sequence.
    ALTER TABLE core_organization ADD COLUMN id bigint;

    CREATE SEQUENCE core_organization_id_seq OWNED BY core_organization.id;
    ALTER TABLE core_organization ALTER COLUMN id SET DEFAULT nextval('core_organization_id_seq');

    UPDATE core_organization SET id = nextval('core_organization_id_seq') WHERE id IS NULL;
    ALTER TABLE core_organization ALTER COLUMN id SET NOT NULL;
    """,
    """
    -- 2) Drop all foreign keys that point at core_organization (currently via code PK).
    DO $$
    DECLARE
        r record;
    BEGIN
        FOR r IN
            SELECT conrelid::regclass::text AS table_name, conname
            FROM pg_constraint
            WHERE contype = 'f' AND confrelid = 'core_organization'::regclass
        LOOP
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.table_name, r.conname);
        END LOOP;
    END $$;
    """,
    """
    -- 3) Replace the primary key on core_organization.
    DO $$
    DECLARE
        pkname text;
    BEGIN
        SELECT conname INTO pkname
        FROM pg_constraint
        WHERE conrelid = 'core_organization'::regclass AND contype = 'p';

        IF pkname IS NOT NULL THEN
            EXECUTE format('ALTER TABLE core_organization DROP CONSTRAINT %I', pkname);
        END IF;
    END $$;

    ALTER TABLE core_organization ADD CONSTRAINT core_organization_pkey PRIMARY KEY (id);
    """,
    """
    -- 4a) Convert core_membershiprequest requested_organization_id from old code (text) to new id (bigint).
    ALTER TABLE core_membershiprequest ADD COLUMN requested_organization_id_new bigint;
    UPDATE core_membershiprequest mr
    SET requested_organization_id_new = o.id
    FROM core_organization o
    WHERE mr.requested_organization_id = o.code;
    """,
    """
    -- 4b) Swap requested_organization_id columns (separate transaction to avoid pending trigger events).
    ALTER TABLE core_membershiprequest DROP COLUMN requested_organization_id;
    ALTER TABLE core_membershiprequest RENAME COLUMN requested_organization_id_new TO requested_organization_id;
    """,
    """
    -- 4c) Convert core_membershiplog target_organization_id from old code (text) to new id (bigint).
    ALTER TABLE core_membershiplog ADD COLUMN target_organization_id_new bigint;
    UPDATE core_membershiplog ml
    SET target_organization_id_new = o.id
    FROM core_organization o
    WHERE ml.target_organization_id = o.code;
    """,
    """
    -- 4d) Swap target_organization_id columns (separate transaction to avoid pending trigger events).
    ALTER TABLE core_membershiplog DROP COLUMN target_organization_id;
    ALTER TABLE core_membershiplog RENAME COLUMN target_organization_id_new TO target_organization_id;
    """,
    """
    -- 4e) Convert core_organizationsponsorship organization_id from old code (text) to new id (bigint).
    ALTER TABLE core_organizationsponsorship ADD COLUMN organization_id_new bigint;
    UPDATE core_organizationsponsorship os
    SET organization_id_new = o.id
    FROM core_organization o
    WHERE os.organization_id = o.code;
    """,
    """
    -- 4f) Swap organization_id columns (separate transaction to avoid pending trigger events).
    ALTER TABLE core_organizationsponsorship DROP COLUMN organization_id;
    ALTER TABLE core_organizationsponsorship RENAME COLUMN organization_id_new TO organization_id;
    """,
    """
    -- 5) Keep historical rendering consistent: snapshot the new org id as text.
    UPDATE core_membershiprequest mr
    SET requested_organization_code = o.id::text,
        requested_organization_name = o.name
    FROM core_organization o
    WHERE mr.requested_organization_id = o.id;

    UPDATE core_membershiplog ml
    SET target_organization_code = o.id::text,
        target_organization_name = o.name
    FROM core_organization o
    WHERE ml.target_organization_id = o.id;
    """,
    """
    -- 6) Drop the old organization code column.
    ALTER TABLE core_organization DROP COLUMN code;
    """,
    """
    -- 7) Recreate the foreign keys + the O2O uniqueness for OrganizationSponsorship.
    ALTER TABLE core_membershiprequest
        ADD CONSTRAINT core_membershiprequest_requested_organization_id_fk
        FOREIGN KEY (requested_organization_id)
        REFERENCES core_organization(id)
        ON DELETE SET NULL;

    ALTER TABLE core_membershiplog
        ADD CONSTRAINT core_membershiplog_target_organization_id_fk
        FOREIGN KEY (target_organization_id)
        REFERENCES core_organization(id)
        ON DELETE SET NULL;

    ALTER TABLE core_organizationsponsorship
        ADD CONSTRAINT core_organizationsponsorship_organization_id_fk
        FOREIGN KEY (organization_id)
        REFERENCES core_organization(id)
        ON DELETE CASCADE;

    ALTER TABLE core_organizationsponsorship
        ADD CONSTRAINT core_organizationsponsorship_organization_id_key UNIQUE (organization_id);
    """,
    """
    -- 8) Restore constraints/indexes that were dropped when swapping FK columns.
    ALTER TABLE core_membershiprequest DROP CONSTRAINT IF EXISTS chk_membershiprequest_exactly_one_target;

    DROP INDEX IF EXISTS uniq_membershiprequest_open_user_type;
    CREATE UNIQUE INDEX uniq_membershiprequest_open_user_type
        ON core_membershiprequest (requested_username, membership_type_id)
        WHERE (status = 'pending' AND requested_organization_id IS NULL AND requested_username <> '');

    DROP INDEX IF EXISTS uniq_membershiprequest_open_org_type;
    CREATE UNIQUE INDEX uniq_membershiprequest_open_org_type
        ON core_membershiprequest (requested_organization_id, membership_type_id)
        WHERE (status = 'pending' AND requested_organization_id IS NOT NULL);

    ALTER TABLE core_membershiprequest
        ADD CONSTRAINT chk_membershiprequest_exactly_one_target
        CHECK (
            (
                requested_organization_id IS NULL
                AND requested_organization_code = ''
                AND requested_username <> ''
            )
            OR (
                requested_username = ''
                AND (requested_organization_id IS NOT NULL OR requested_organization_code <> '')
            )
        );

    ALTER TABLE core_membershiplog DROP CONSTRAINT IF EXISTS chk_membershiplog_exactly_one_target;

    ALTER TABLE core_membershiplog
        ADD CONSTRAINT chk_membershiplog_exactly_one_target
        CHECK (
            (
                target_username = ''
                AND (target_organization_id IS NOT NULL OR target_organization_code <> '')
            )
            OR (
                target_username <> ''
                AND target_organization_id IS NULL
                AND target_organization_code = ''
            )
        );

    DROP INDEX IF EXISTS mr_org_status;
    CREATE INDEX mr_org_status ON core_membershiprequest (requested_organization_id, status);

    DROP INDEX IF EXISTS ml_org_at;
    CREATE INDEX ml_org_at ON core_membershiplog (target_organization_id, created_at);

    DROP INDEX IF EXISTS ml_org_act_at;
    CREATE INDEX ml_org_act_at ON core_membershiplog (target_organization_id, action, created_at);
    """,
]


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0027_remove_membershiplog_chk_membershiplog_exactly_one_target_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(_ORG_INT_PK_SQL, reverse_sql=migrations.RunSQL.noop),
            ],
            state_operations=[
                migrations.RemoveField(model_name="organization", name="code"),
                migrations.AddField(
                    model_name="organization",
                    name="id",
                    field=models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                migrations.AlterModelOptions(
                    name="organization",
                    options={"ordering": ("name", "id")},
                ),
            ],
        ),
    ]
