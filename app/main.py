from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import streamlit as st

from app.config import Settings
from app.services.agent_service import analyse_judgment
from app.services.debug_service import save_debug_extraction
from app.services.pdf_service import read_pdf
from app.services.snowflake_service import (
    generate_streamlit_embed_url,
    save_extraction,
)
from app.services.validation_service import validate_extraction


load_dotenv()

st.set_page_config(
    page_title="NZ Court Intelligence",
    page_icon="⚖️",
    layout="wide",
)

settings = Settings.from_env()

st.title("NZ Court Intelligence")
st.caption(
    "Public judgment exploration using Amazon Bedrock + Strands Agent + Snowflake + dbt"
)

with st.sidebar:
    st.subheader("Runtime")
    st.write(f"AWS region: `{settings.aws_region}`")
    st.write(
        "Bedrock model: "
        + (f"`{settings.bedrock_model_id}`" if settings.bedrock_model_id else "not configured")
    )

    st.info(
        "Use only documents that may lawfully be processed and republished. "
        "The marker scan is a review aid, not a legal determination."
    )

source_url = st.text_input(
    "Official/public source URL (optional)",
    placeholder="https://...",
)

uploaded = st.file_uploader(
    "Upload a public NZ court judgment PDF",
    type=["pdf"],
)

default_request = (
    "Extract the case metadata, legal topics, key legal issues, legislation cited, "
    "cases cited, judge, outcome, and supporting page-level evidence."
)

user_request = st.text_area(
    "Agent task",
    value=default_request,
    height=120,
)

if uploaded is not None:
    raw_bytes = uploaded.getvalue()

    try:
        document = read_pdf(
            filename=uploaded.name,
            raw_bytes=raw_bytes,
            source_url=source_url,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Pages", document.page_count)
        c2.metric("Document SHA", document.sha256[:12] + "…")
        c3.metric("Source", "Provided" if document.source_url else "Upload only")

        if st.button("Run agent", type="primary"):
            with st.spinner("Agent is inspecting and validating the judgment..."):
                extraction = analyse_judgment(
                    document=document,
                    user_request=user_request,
                    settings=settings,
                )
                try:
                    debug_path = save_debug_extraction(extraction, document)
                except OSError as exc:
                    debug_path = None
                    st.warning(f"Could not save debug extraction: {exc}")
                validation = validate_extraction(
                    extraction=extraction,
                    document=document,
                )

            st.session_state["document"] = document
            st.session_state["extraction"] = extraction
            st.session_state["validation"] = validation
            st.session_state["debug_path"] = debug_path

    except Exception as exc:
        st.error(str(exc))

if "extraction" in st.session_state:
    extraction = st.session_state["extraction"]
    validation = st.session_state["validation"]
    document = st.session_state["document"]
    debug_path = st.session_state.get("debug_path")

    st.divider()

    status_col, ref_col, evidence_col = st.columns(3)
    status_col.metric("Validation", validation.status)
    ref_col.metric(
        "References verified",
        len(validation.verified_references),
    )
    evidence_col.metric(
        "Evidence verified",
        f"{validation.evidence_verified}/{validation.evidence_total}",
    )

    if validation.status == "ACCEPTED":
        st.success("Deterministic checks passed. Review before using the result.")
    else:
        st.warning("Human review is required before treating this extraction as verified.")

    if validation.reasons:
        st.subheader("Review reasons")
        for reason in validation.reasons:
            st.write(f"- {reason}")

    tab1, tab2 = st.tabs(["Structured extraction", "Validation"])

    with tab1:
        st.json(extraction.model_dump(mode="json"))
        if debug_path is not None:
            st.caption(f"Debug JSON saved to `{debug_path}`")

    with tab2:
        st.json(validation.model_dump(mode="json"))

    reviewed = st.checkbox(
        "I reviewed this extraction and understand that publication restrictions may require separate legal verification."
    )

    if st.button(
        "Save extraction to Snowflake",
        disabled=not reviewed,
    ):
        try:
            extraction_id = save_extraction(
                document=document,
                extraction=extraction,
                validation=validation,
                settings=settings,
            )
            st.success(f"Saved to Snowflake. Extraction ID: {extraction_id}")
        except Exception as exc:
            st.error(f"Snowflake write failed: {exc}")
        else:
            try:
                embed_url = generate_streamlit_embed_url(settings)
            except Exception as exc:
                st.warning(f"Saved, but the dashboard link could not be created: {exc}")
            else:
                st.link_button(
                    "Open Snowflake dashboard",
                    embed_url,
                    type="primary",
                )
