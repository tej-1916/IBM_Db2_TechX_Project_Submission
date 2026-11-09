from civiclens.db.migrate import load_statements


def test_schema_sql_parses_into_known_objects():
    stmts = load_statements()
    tables = {s.name for s in stmts if s.kind == "TABLE"}
    assert tables == {
        "COMPLAINTS",
        "INVESTIGATIONS",
        "INVESTIGATION_EVIDENCE",
        "RECOMMENDATIONS",
        "REVIEW_DECISIONS",
        "AUDIT_LOG",
    }
    assert all("{schema}." in s.template for s in stmts)
    # tables must be created before the indexes / FKs that reference them
    names = [s.name for s in stmts]
    assert names.index("COMPLAINTS") < names.index("IX_COMPLAINTS_CAT_TIME")
    assert names.index("INVESTIGATIONS") < names.index("RECOMMENDATIONS") < names.index("REVIEW_DECISIONS")
