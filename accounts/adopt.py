from django.db.migrations.recorder import MigrationRecorder


def adopt_auth_user(connection) -> bool:
    """Mark accounts.0001_initial applied on a database that already has auth_user.

    Existing databases created auth_user under auth.User; accounts.User
    takes over that very table, so 0001 must not try to create it again.
    Recording it as applied is the one-time switch (see the email-login
    spec, "The one-time switch"). Returns True only when it recorded it,
    so migrate can say so once. A fresh database has no auth_user yet and
    migrates normally.
    """
    if "auth_user" not in connection.introspection.table_names():
        return False
    recorder = MigrationRecorder(connection)
    recorder.ensure_schema()
    if recorder.migration_qs.filter(app="accounts", name="0001_initial").exists():
        return False
    recorder.record_applied("accounts", "0001_initial")
    return True
