from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import boto3

from app.config import Settings


load_dotenv()
settings = Settings.from_env()
settings.require_bedrock()

client = boto3.client(
    "bedrock-runtime",
    region_name=settings.aws_region,
)

response = client.converse(
    modelId=settings.bedrock_model_id,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "Reply with exactly: BEDROCK_OK"
                    )
                }
            ],
        }
    ],
    inferenceConfig={
        "maxTokens": 30,
        "temperature": 0,
    },
)

print(response["output"]["message"]["content"][0]["text"])
