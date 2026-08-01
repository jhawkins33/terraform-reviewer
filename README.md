# Terraform Reviewer

A Streamlit web app that reviews Terraform HCL code for security issues and best practices, powered by Claude via Amazon Bedrock.

Paste any Terraform configuration and get structured feedback organized by severity — HIGH, MEDIUM, and LOW — with specific explanations and suggested fixes for each finding.

## What it catches

- **Security**: overly permissive IAM policies, missing S3 encryption, public access enabled, missing bucket policies
- **Best practices**: missing tags, access logging not configured, hardcoded values that should be variables
- **Cost/Reliability**: missing versioning, single-AZ deployments, unoptimized instance types

## Architecture

User pastes HCL → Streamlit UI → Claude (Bedrock) → structured JSON findings → rendered UI
No vector search, no persistent infrastructure — just a Bedrock API call per review. Cheap, fast, and stateless.

## Setup

**Prerequisites:** Python 3.12, an AWS account with Bedrock access, AWS CLI configured with a named profile.

```bash
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt

cp .env.example .env
# edit .env with your AWS profile name

streamlit run app.py
```

Opens at `http://localhost:8501`.

## Example

Reviewing a minimal S3 bucket + IAM role with `AdministratorAccess` returns:

- 🔴 **HIGH**: AdministratorAccess policy violates least privilege
- 🔴 **HIGH**: S3 bucket lacks encryption configuration
- 🔴 **HIGH**: S3 bucket allows public access by default
- 🔴 **HIGH**: S3 bucket versioning not enabled
- 🟡 **MEDIUM**: S3 bucket lacks access logging
- 🟡 **MEDIUM**: Missing bucket policy for explicit access control

## Roadmap

- [x] Core review engine (Claude via Bedrock)
- [x] Streamlit UI with severity-grouped findings
- [x] File upload support (review `.tf` files directly)
- [x] Multi-file / directory review
- [ ] Export findings as markdown or JSON report
- [ ] Comparison mode (before/after review)