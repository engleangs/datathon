"""Provision the Snowflake ingestion role and service user safely.

The target service-user password comes from SNOWFLAKE_PASSWORD in the local
.env file. Administrative authentication comes from a named Snowflake
connection, so an administrator password does not need to be stored with the
application's runtime secrets.
"""

from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
import re

from dotenv import load_dotenv
import snowflake.connector
from snowflake.connector.util_text import split_statements


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "003_CreateIngestionAgentRoles.sql"
PASSWORD_BIND = re.compile(r"\bPASSWORD\s*=\s*\?", re.IGNORECASE)


def provision(connection, password: str) -> None:
    """Execute the provisioning SQL, binding the password as data."""

    sql = SQL_PATH.read_text(encoding="utf-8")
    password_statement_count = 0

    with connection.cursor() as cursor:
        for statement, _is_put_or_get in split_statements(StringIO(sql)):
            statement = statement.strip()
            if not statement:
                continue

            if PASSWORD_BIND.search(statement):
                password_statement_count += 1
                cursor.execute(statement, (password,))
            else:
                cursor.execute(statement)

    if password_statement_count != 1:
        raise RuntimeError(
            "Expected exactly one password bind in "
            f"{SQL_PATH}, found {password_statement_count}."
        )


def main() -> None:
    load_dotenv(ROOT / ".env")

    password = os.getenv("SNOWFLAKE_PASSWORD", "")
    if not password:
        raise RuntimeError("SNOWFLAKE_PASSWORD is not set in .env.")

    connection_name = os.getenv("SNOWFLAKE_ADMIN_CONNECTION", "default").strip()
    if not connection_name:
        raise RuntimeError("SNOWFLAKE_ADMIN_CONNECTION must not be empty.")

    connection = snowflake.connector.connect(
        connection_name=connection_name,
        paramstyle="qmark",
    )
    try:
        provision(connection, password)
    finally:
        connection.close()

    print(
        "Provisioned INGESTION_AGENT_SVC and updated its password from .env "
        f"using Snowflake connection {connection_name!r}."
    )


if __name__ == "__main__":
    main()
