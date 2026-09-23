from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import snowflake.connector

from app.config import Settings


load_dotenv()
settings = Settings.from_env()
settings.require_snowflake()

kwargs = {
    "account": settings.snowflake_account,
    "user": settings.snowflake_user,
    "password": settings.snowflake_password,
    "warehouse": settings.snowflake_warehouse,
    "database": settings.snowflake_database,
    "schema": settings.snowflake_schema,
}

if settings.snowflake_role:
    kwargs["role"] = settings.snowflake_role

conn = snowflake.connector.connect(**kwargs)

try:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT CURRENT_ACCOUNT(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE()"
    )
    print(cursor.fetchone())
finally:
    conn.close()
