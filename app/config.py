from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    aws_region: str
    bedrock_model_id: str

    snowflake_account: str
    snowflake_user: str
    snowflake_password: str
    snowflake_warehouse: str
    snowflake_database: str
    snowflake_schema: str
    snowflake_role: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            aws_region=os.getenv("AWS_REGION", "ap-southeast-2"),
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "").strip(),
            snowflake_account=os.getenv("SNOWFLAKE_ACCOUNT", "").strip(),
            snowflake_user=os.getenv("SNOWFLAKE_USER", "").strip(),
            snowflake_password=os.getenv("SNOWFLAKE_PASSWORD", "").strip(),
            snowflake_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH").strip(),
            snowflake_database=os.getenv(
                "SNOWFLAKE_DATABASE", "NZ_COURT_INTELLIGENCE"
            ).strip(),
            snowflake_schema=os.getenv("SNOWFLAKE_SCHEMA", "RAW").strip(),
            snowflake_role=os.getenv("SNOWFLAKE_ROLE", "").strip(),
        )

    def require_bedrock(self) -> None:
        if not self.bedrock_model_id:
            raise RuntimeError(
                "BEDROCK_MODEL_ID is not configured. Set it in .env or your secret store."
            )

    def require_snowflake(self) -> None:
        missing = []
        for name, value in (
            ("SNOWFLAKE_ACCOUNT", self.snowflake_account),
            ("SNOWFLAKE_USER", self.snowflake_user),
            ("SNOWFLAKE_PASSWORD", self.snowflake_password),
            ("SNOWFLAKE_WAREHOUSE", self.snowflake_warehouse),
            ("SNOWFLAKE_DATABASE", self.snowflake_database),
        ):
            if not value:
                missing.append(name)

        if missing:
            raise RuntimeError(
                "Missing Snowflake configuration: " + ", ".join(missing)
            )
