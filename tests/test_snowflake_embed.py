import json
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.snowflake_service import generate_streamlit_embed_url


def _settings(monkeypatch, **overrides):
    values = {
        "SNOWFLAKE_ACCOUNT_URL": "https://account.snowflakecomputing.com",
        "SNOWFLAKE_EMBED_PAT": "secret-token",
        "SNOWFLAKE_EMBED_ROLE": "STREAMLIT_EMBED_ROLE",
        "STREAMLIT_DATABASE": "DATATHON TEST",
        "STREAMLIT_SCHEMA": "COURTLENS",
        "STREAMLIT_APP": "TESTCOURTDASHBOARD",
        "PARENT_ORIGIN": "https://datathon.example.com",
    }
    values.update(overrides)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def test_generate_streamlit_embed_url(monkeypatch):
    settings = _settings(monkeypatch)
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"embed_url": "https://app.snowflake.com/embed/single-use"}
    ).encode("utf-8")
    response.__enter__.return_value = response

    with patch("app.services.snowflake_service.urlopen", return_value=response) as mocked:
        embed_url = generate_streamlit_embed_url(settings)

    request = mocked.call_args.args[0]
    headers = dict(request.header_items())
    assert request.full_url.endswith(
        "/api/v2/databases/DATATHON%20TEST/schemas/COURTLENS/"
        "streamlits/TESTCOURTDASHBOARD:generate-embed-url"
    )
    assert request.get_method() == "POST"
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-snowflake-role"] == "STREAMLIT_EMBED_ROLE"
    assert json.loads(request.data) == {
        "parent_origin": "https://datathon.example.com"
    }
    assert embed_url == "https://app.snowflake.com/embed/single-use"


def test_generate_streamlit_embed_url_requires_pat(monkeypatch):
    settings = _settings(monkeypatch, SNOWFLAKE_EMBED_PAT="")

    with pytest.raises(RuntimeError, match="SNOWFLAKE_EMBED_PAT"):
        generate_streamlit_embed_url(settings)
