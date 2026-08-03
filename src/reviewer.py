"""
Core Terraform review logic -- sends HCL code to Claude via Bedrock
and returns structured security/best-practice feedback.
"""

import json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "churn-mlops-personal")
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

PROMPT_TEMPLATE = """You are an expert Terraform and AWS security reviewer. Analyze the following Terraform code and return structured feedback.

For each issue found, assign:
- severity: HIGH (security risk or data loss), MEDIUM (best practice violation), or LOW (minor improvement)
- category: one of Security, Best Practice, Cost, or Reliability
- title: a short (< 10 word) description of the issue
- detail: 2-3 sentences explaining the problem and the specific fix

Return ONLY a valid JSON object in this exact format, no markdown fences, no other text:
{
  "summary": "one sentence overall assessment",
  "findings": [
    {
      "severity": "HIGH",
      "category": "Security",
      "title": "Short title here",
      "detail": "Explanation and fix here."
    }
  ]
}

If no issues are found, return an empty findings list with a positive summary.

Terraform code to review:

HCL_CODE_START
TERRAFORM_CODE
HCL_CODE_END"""


def get_bedrock_client():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return session.client("bedrock-runtime")


def review_terraform(hcl_code: str, bedrock=None) -> dict:
    """
    Review a block of Terraform HCL code and return structured feedback.

    Returns a dict with:
        - summary: one-sentence overall assessment
        - findings: list of dicts, each with:
            - severity: HIGH / MEDIUM / LOW
            - category: Security / Best Practice / Cost / Reliability
            - title: short description
            - detail: explanation and suggested fix
    """
    if bedrock is None:
        bedrock = get_bedrock_client()

    prompt = PROMPT_TEMPLATE.replace("TERRAFORM_CODE", hcl_code)

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    result = json.loads(response["body"].read())
    raw = result["content"][0]["text"].strip()

    # Strip markdown fences if Claude wraps the JSON anyway
    clean = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {
            "summary": "Could not parse review response.",
            "findings": [],
            "raw": raw,
        }
def findings_to_markdown(result: dict, title: str = "Terraform Review Report") -> str:
    """Generate a markdown report from a review result dict."""
    from datetime import datetime

    lines = [
        f"# {title}",
        f"",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        f"",
        f"## Summary",
        f"",
        result.get("summary", "No summary available."),
        f"",
        f"## Findings",
        f"",
    ]

    findings = result.get("findings", [])
    if not findings:
        lines.append("No issues found.")
    else:
        for severity in ["HIGH", "MEDIUM", "LOW"]:
            group = [f for f in findings if f["severity"] == severity]
            if group:
                lines.append(f"### {severity} ({len(group)})")
                lines.append("")
                for finding in group:
                    lines.append(f"**{finding['category']} — {finding['title']}**")
                    lines.append("")
                    lines.append(finding["detail"])
                    lines.append("")

    return "\n".join(lines)


def multi_findings_to_markdown(results: dict) -> str:
    """Generate a combined markdown report for a multi-file review."""
    from datetime import datetime

    all_findings = []
    for r in results.values():
        all_findings.extend(r.get("findings", []))

    total_high = sum(1 for f in all_findings if f["severity"] == "HIGH")
    total_medium = sum(1 for f in all_findings if f["severity"] == "MEDIUM")
    total_low = sum(1 for f in all_findings if f["severity"] == "LOW")

    lines = [
        "# Terraform Multi-File Review Report",
        "",
        "*Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "*",
        "*Files reviewed: " + str(len(results)) + "*",
        "",
        "## Summary",
        "",
        "| Severity | Count |",
        "|---|---|",
        "| HIGH | " + str(total_high) + " |",
        "| MEDIUM | " + str(total_medium) + " |",
        "| LOW | " + str(total_low) + " |",
        "",
        "## Per-File Results",
        "",
    ]

    for filename, result in results.items():
        lines.append("### " + filename)
        lines.append("")
        lines.append(result.get("summary", ""))
        lines.append("")
        findings = result.get("findings", [])
        if not findings:
            lines.append("No issues found.")
        else:
            for f in findings:
                lines.append(
                    "- **" + f["severity"] + "** (" + f["category"] + ") -- "
                    + f["title"] + ": " + f["detail"]
                )
        lines.append("")

    return "\n".join(lines)