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

    snowflake_account_url: str
    snowflake_embed_pat: str
    snowflake_embed_role: str
    streamlit_database: str
    streamlit_schema: str
    streamlit_app: str
    parent_origin: str

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
            snowflake_account_url=os.getenv("SNOWFLAKE_ACCOUNT_URL", "").strip(),
            snowflake_embed_pat=os.getenv("SNOWFLAKE_EMBED_PAT", "").strip(),
            snowflake_embed_role=os.getenv("SNOWFLAKE_EMBED_ROLE", "").strip(),
            streamlit_database=os.getenv("STREAMLIT_DATABASE", "").strip(),
            streamlit_schema=os.getenv("STREAMLIT_SCHEMA", "").strip(),
            streamlit_app=os.getenv("STREAMLIT_APP", "").strip(),
            parent_origin=os.getenv("PARENT_ORIGIN", "").strip(),
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

    def require_snowflake_embed(self) -> None:
        missing = []
        for name, value in (
            ("SNOWFLAKE_ACCOUNT_URL", self.snowflake_account_url),
            ("SNOWFLAKE_EMBED_PAT", self.snowflake_embed_pat),
            ("SNOWFLAKE_EMBED_ROLE", self.snowflake_embed_role),
            ("STREAMLIT_DATABASE", self.streamlit_database),
            ("STREAMLIT_SCHEMA", self.streamlit_schema),
            ("STREAMLIT_APP", self.streamlit_app),
            ("PARENT_ORIGIN", self.parent_origin),
        ):
            if not value:
                missing.append(name)

        if missing:
            raise RuntimeError(
                "Missing Snowflake Streamlit embed configuration: "
                + ", ".join(missing)
            )
