"""
Ansible playbook review logic -- sends YAML playbook content to Claude
via Bedrock and returns structured security/best-practice feedback.
"""

import json
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "churn-mlops-personal")
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

ANSIBLE_PROMPT_TEMPLATE = """You are an expert Ansible and DevOps security reviewer. Analyze the following Ansible playbook and return structured feedback.

For each issue found, assign:
- severity: HIGH (security risk or data exposure), MEDIUM (best practice violation), or LOW (minor improvement)
- category: one of Security, Best Practice, Reliability, or Performance
- title: a short (< 10 word) description of the issue
- detail: 2-3 sentences explaining the problem and the specific fix

Common Ansible issues to look for:
- Hardcoded credentials, passwords, or secrets (use Ansible Vault instead)
- Missing no_log: true on tasks that handle sensitive data
- Overly broad become/become_user usage (privilege escalation without need)
- Tasks missing a name field (makes debugging hard)
- Using shell/command modules where purpose-built modules exist
- Missing error handling (ignore_errors without justification)
- Deprecated modules or syntax
- Missing handlers for service restarts
- World-readable file permissions set via file module
- Using latest for package versions (non-idempotent)

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

Ansible playbook to review:

PLAYBOOK_START
ANSIBLE_CODE
PLAYBOOK_END"""


def get_bedrock_client():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return session.client("bedrock-runtime")


def review_ansible(playbook_code: str, bedrock=None) -> dict:
    """
    Review an Ansible playbook and return structured feedback.

    Returns a dict with:
        - summary: one-sentence overall assessment
        - findings: list of dicts, each with:
            - severity: HIGH / MEDIUM / LOW
            - category: Security / Best Practice / Reliability / Performance
            - title: short description
            - detail: explanation and suggested fix
    """
    if bedrock is None:
        bedrock = get_bedrock_client()

    prompt = ANSIBLE_PROMPT_TEMPLATE.replace("ANSIBLE_CODE", playbook_code)

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

    clean = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {
            "summary": "Could not parse review response.",
            "findings": [],
            "raw": raw,
        }


def ansible_findings_to_markdown(result: dict, title: str = "Ansible Playbook Review Report") -> str:
    """Generate a markdown report from an Ansible review result dict."""
    from datetime import datetime

    lines = [
        "# " + title,
        "",
        "*Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "*",
        "",
        "## Summary",
        "",
        result.get("summary", "No summary available."),
        "",
        "## Findings",
        "",
    ]

    findings = result.get("findings", [])
    if not findings:
        lines.append("No issues found.")
    else:
        for severity in ["HIGH", "MEDIUM", "LOW"]:
            group = [f for f in findings if f["severity"] == severity]
            if group:
                lines.append("### " + severity + " (" + str(len(group)) + ")")
                lines.append("")
                for finding in group:
                    lines.append("**" + finding["category"] + " -- " + finding["title"] + "**")
                    lines.append("")
                    lines.append(finding["detail"])
                    lines.append("")

    return "\n".join(lines)