"""Apply the repository's schema migrations in order. Phase 8 P8-OWR-003.

Charlie's Decision 3 Correction Ruling section 3: the repository becomes the
reproducible source for rebuilding the accepted schema. Manual DDL in Supabase
remains the evidence of what was applied to the current live database.

WHY A RUNNER AND NOT ALEMBIC

Alembic would bring autogenerate, branching and a whole second model of the
schema into a project that has never had one, on the day a control constraint
was found to be wrong. This does one thing: apply ordered, guarded SQL files
and record which ones ran. Every file is independently safe to re-run, so the
ledger is a convenience rather than the thing correctness depends on - if the
ledger were lost, re-running everything would still be a no-op.

Object names in the migration files are UNQUALIFIED. The schema is set here via
search_path, which is what lets the same artifacts be proved against a
disposable test schema rather than only against production.

Usage:
    python migrate.py --schema rigid_foam --dry-run
    python migrate.py --schema rigid_foam
    python migrate.py --schema rigid_foam --baseline
"""
import argparse
import hashlib
import os
import sys

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")

LEDGER_DDL = """
create table if not exists schema_migrations (
    version varchar(255) primary key,
    checksum varchar(64) not null,
    applied_at timestamp not null default (now() at time zone 'utc'),
    baselined boolean not null default false
)
"""


def migration_files():
    """Every .sql file, in filename order. The NNNN_ prefix is the ordering."""
    names = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))
    for name in names:
        path = os.path.join(MIGRATIONS_DIR, name)
        with open(path, encoding="utf-8") as handle:
            sql = handle.read()
        yield name[: -len(".sql")], sql


def _checksum(sql):
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def applied_versions(connection):
    from sqlalchemy import text

    rows = connection.execute(text("select version, checksum from schema_migrations")).fetchall()
    return {row[0]: row[1] for row in rows}


def run(database_url, schema, dry_run=False, baseline=False, verbose=True):
    """Returns the list of versions applied (or that would be).

    Each migration runs in its own transaction together with its ledger insert,
    so a failure leaves neither the change nor the claim that it was made.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    applied_now = []

    with engine.begin() as connection:
        connection.execute(text(f'set search_path to "{schema}"'))
        connection.execute(text(LEDGER_DDL))

    with engine.connect() as connection:
        connection.execute(text(f'set search_path to "{schema}"'))
        already = applied_versions(connection)

    for version, sql in migration_files():
        checksum = _checksum(sql)
        if version in already:
            if already[version] != checksum:
                # Not fatal, but it means the repository no longer describes
                # what was applied - which is the whole point of the ledger.
                print(f"WARNING {version}: checksum differs from the applied copy", file=sys.stderr)
            elif verbose:
                print(f"skip    {version} (already applied)")
            continue

        if dry_run:
            print(f"would   {version}")
            applied_now.append(version)
            continue

        with engine.begin() as connection:
            connection.execute(text(f'set search_path to "{schema}"'))
            if not baseline:
                connection.exec_driver_sql(sql)
            connection.execute(
                text(
                    "insert into schema_migrations (version, checksum, baselined) "
                    "values (:v, :c, :b)"
                ),
                {"v": version, "c": checksum, "b": baseline},
            )
        applied_now.append(version)
        if verbose:
            print(f"{'baseline' if baseline else 'apply   '} {version}")

    return applied_now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="rigid_foam")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="record the migrations as applied WITHOUT executing them - for a "
             "database where the DDL was already applied by hand",
    )
    args = parser.parse_args()

    if not args.database_url:
        parser.error("no database URL: pass --database-url or set DATABASE_URL")

    applied = run(args.database_url, args.schema, dry_run=args.dry_run, baseline=args.baseline)
    if not applied:
        print("nothing to do - schema is up to date")


if __name__ == "__main__":
    main()
