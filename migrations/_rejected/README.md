# Rejected migration attempts

Artifacts in this folder are **not** part of the active migration set. The
runner (`migrate.py`) discovers migrations with `os.listdir(MIGRATIONS_DIR)`,
which does not recurse, so nothing here is ever applied. The schema-agnostic
conformance test scans the same way and does not reach here either.

A file lands here only under an explicit ruling from Charlie, and only for a
migration attempt that failed QA **before** release — never for one that was
committed, pushed, accepted at a gate, or shipped in a baseline. Those stay
immutable in the active set and are corrected by a later artifact.

Each rejection keeps two files: the artifact exactly as it was applied, and a
`.evidence.txt` recording why it was rejected, what the database looked like
before and after the rollback, and which checksum became authoritative.
