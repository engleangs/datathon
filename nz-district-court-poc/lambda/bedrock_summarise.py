"""Snowflake external function -> API Gateway -> this Lambda -> Amazon Bedrock.

Job: the "sentencing arithmetic" for District Court sentencing notes.
Cortex AI_EXTRACT reads the simple fields for every decision. This function
does the part that needs reasoning: turn the judge's words into a starting
point, a list of uplifts and discounts (percent and months), and an end
sentence in months. Civil decisions get amounts instead.

Snowflake sends rows in batches:
    {"data": [[row_number, decision_text, case_type], ...]}
We return one row per input row, in the same order:
    {"data": [[row_number, {...json...}], ...]}
"""

import json
import os

import boto3
from botocore.config import Config

MODEL_ID = os.environ["MODEL_ID"]
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1500"))
# Hard cap on input size. Protects cost. About 4 characters per token.
MAX_INPUT_CHARS = int(os.environ.get("MAX_INPUT_CHARS", "150000"))

bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=110),
)

SYSTEM_PROMPT = """You analyse decisions of the District Court of New Zealand.
You return JSON only. Use only facts stated in the decision.
If a value is not stated, use null. Do not guess numbers.
Never write the name of the defendant, a victim, a complainant or a witness.
Convert all durations to months (1 year = 12 months, 1 week = 0.25 months)."""

USER_TEMPLATE = """Case type hint: {case_type}

Return JSON with exactly these keys:
- "document_type": one of "sentencing", "reserved judgment", "oral judgment", "appeal", "other"
- "lead_offence": the most serious offence, in a few words (no names)
- "starting_point_months": the starting point the judge adopted, in months
- "adjustments": a list, in the order the judge applied them. Each item is:
    {{"factor": short description,
      "category": one of "previous_convictions", "offending_on_bail_or_sentence",
                  "guilty_plea", "remorse", "youth", "cultural_background_s27",
                  "rehabilitation", "addiction", "mental_health", "good_character",
                  "family_circumstances", "totality", "other",
      "direction": "uplift" or "discount",
      "percent": number or null,
      "months": number or null}}
- "guilty_plea_percent": the guilty plea discount in percent, or null
- "personal_mitigation_percent": the SUM of discounts for personal mitigating factors
    (remorse, youth, s 27 background, rehabilitation, addiction, mental health,
    good character, family circumstances), in percent, or null. Do NOT include the guilty plea.
- "end_sentence_months": the final sentence length in months, or null
- "sentence_type": one of "imprisonment", "home detention", "community detention",
    "intensive supervision", "supervision", "community work", "fine",
    "discharge without conviction", "conviction and discharge", "other", or null
- "home_detention_considered": true or false
- "reparation_nzd": total reparation ordered in NZ dollars, or null
- "amount_claimed_nzd": civil only, or null
- "amount_awarded_nzd": civil only, or null
- "costs_awarded_nzd": civil only, or null
- "outcome": one short sentence on the result (no names)
- "confidence": your confidence in the numbers, from 0.0 to 1.0

Decision text:
<decision>
{text}
</decision>"""


def _brief(text: str, case_type: str) -> dict:
    if not text:
        return {"error": "empty input"}

    truncated = len(text) > MAX_INPUT_CHARS
    if truncated:
        # Keep the start (charges, facts) and the end (the calculation and sentence).
        half = MAX_INPUT_CHARS // 2
        text = text[:half] + "\n\n[... middle omitted ...]\n\n" + text[-half:]

    resp = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{
            "role": "user",
            "content": [{"text": USER_TEMPLATE.format(case_type=case_type or "unknown", text=text)}],
        }],
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0},
    )

    raw = resp["output"]["message"]["content"][0]["text"].strip()
    try:
        result = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        result = {"error": "model did not return valid JSON", "raw": raw[:2000]}

    usage = resp.get("usage", {})
    result["_meta"] = {
        "model_id": MODEL_ID,
        "input_tokens": usage.get("inputTokens"),
        "output_tokens": usage.get("outputTokens"),
        "input_truncated": truncated,
    }
    return result


def handler(event, context):
    body = event.get("body")
    payload = json.loads(body) if isinstance(body, str) else (body or event)
    rows = payload.get("data", [])

    out = []
    for row in rows:
        row_number = row[0]
        text = row[1] if len(row) > 1 else None
        case_type = row[2] if len(row) > 2 else None
        try:
            out.append([row_number, _brief(text, case_type)])
        except Exception as exc:  # one bad row must not fail the whole batch
            out.append([row_number, {"error": type(exc).__name__, "detail": str(exc)[:500]}])

    return {"statusCode": 200, "body": json.dumps({"data": out})}
