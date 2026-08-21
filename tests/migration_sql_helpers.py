"""Shared readers for controlled migration artifacts.

These live outside any one test file because two test files parse the same
SQL for the same reason, and the first version of the parser had a hole that
would otherwise have to be found and fixed twice.

Not named test_*.py so pytest does not collect it. Its own coverage lives in
tests/test_r3_production_unit_inventory.py::test_the_scope_check_can_see_a_second_assignment.
"""
import os
import re


def statements(sql, starting_with):
    """The statements in a migration that begin with a given phrase.

    Whole-line comments are stripped first. Without that the leading comment
    block glues itself to the first statement and the count comes out one
    short - a real failure on the R2 correction test's first run, and the same
    prose-versus-code trap as the R1 terminology scanner.
    """
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in code.split(";")
            if s.strip().lower().startswith(starting_with.lower())]


def code_without_comments(sql):
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))


def set_targets(statement):
    """Every column an UPDATE assigns, not just the first one.

    Written after a mutation survived. The obvious form -
    re.findall(r"set\\s+(\\w+)\\s*=", stmt) - only ever matches the column
    directly after the SET keyword, because a second assignment arrives as
    ", name = ..." with no "set" in front of it. So a migration widened from

        set production_unit_id = u.id
    to  set production_unit_id = u.id, name = m.name

    passed a test whose whole job was to refuse exactly that.

    The SET clause is cut at the first FROM or WHERE - an UPDATE ... FROM
    clause carries its own commas - and then split.
    """
    body = re.split(r"\bset\b", statement, maxsplit=1, flags=re.IGNORECASE)[1]
    body = re.split(r"\b(?:from|where)\b", body, maxsplit=1, flags=re.IGNORECASE)[0]
    return [m.group(1) for m in re.finditer(r"([A-Za-z_]\w*)\s*=", body)]


def read_migration(migrations_dir, filename):
    return open(os.path.join(migrations_dir, filename), encoding="utf-8").read()
