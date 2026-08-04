"""
Terraform Reviewer -- Streamlit UI.

Three modes:
  - Single file: paste or upload one .tf file for review
  - Multi-file: upload multiple .tf files for a full project review
  - Compare: review original and revised code side-by-side

Usage:
    streamlit run app.py
"""

import streamlit as st
from src.reviewer import get_bedrock_client, review_terraform, findings_to_markdown, multi_findings_to_markdown
from src.ansible_reviewer import review_ansible, ansible_findings_to_markdown

st.set_page_config(
    page_title="Terraform Reviewer",
    page_icon="🔍",
    layout="wide",
)

SEVERITY_COLORS = {
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}

EXAMPLE_CODE = """\
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"
}

resource "aws_iam_role_policy_attachment" "admin" {
  role       = aws_iam_role.example.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
"""

EXAMPLE_FIXED = """\
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"tab_single, 
}

resource "aws_s3_bucket_public_access_block" "example" {
  bucket                  = aws_s3_bucket.example.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "example" {
  bucket = aws_s3_bucket.example.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_iam_role_policy_attachment" "sagemaker" {
  role       = aws_iam_role.example.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerReadOnly"
}
"""

EXAMPLE_ANSIBLE = """\
---
- name: Deploy web application
  hosts: all
  become: true
  tasks:
    - shell: apt-get update && apt-get install -y nginx

    - copy:
        content: "db_password: supersecret123"
        dest: /etc/app/config.yml
        mode: '0644'

    - apt:
        name: python3
        state: latest

    - service:
        name: nginx
        state: started
"""


@st.cache_resource
def load_bedrock():
    return get_bedrock_client()


def render_findings(findings):
    if not findings:
        st.success("No issues found — looks good!")
        return
    high = [f for f in findings if f["severity"] == "HIGH"]
    medium = [f for f in findings if f["severity"] == "MEDIUM"]
    low = [f for f in findings if f["severity"] == "LOW"]
    for group, label in [(high, "HIGH"), (medium, "MEDIUM"), (low, "LOW")]:
        if group:
            st.markdown(f"**{SEVERITY_COLORS[label]} {label}** ({len(group)})")
            for finding in group:
                with st.expander(f"{finding['category']} — {finding['title']}"):
                    st.markdown(finding["detail"])


def finding_key(f):
    """Stable key for deduplicating findings across before/after."""
    return f"{f['severity']}|{f['category']}|{f['title']}"


def compare_findings(before, after):
    """
    Classify findings into resolved, new, and remaining.
    Uses (severity, category, title) as a stable identity key.
    """
    before_keys = {finding_key(f): f for f in before}
    after_keys = {finding_key(f): f for f in after}

    resolved = [f for k, f in before_keys.items() if k not in after_keys]
    new = [f for k, f in after_keys.items() if k not in before_keys]
    remaining = [f for k, f in after_keys.items() if k in before_keys]

    return resolved, new, remaining


st.title("🔍 Terraform Reviewer")
st.caption("Powered by Claude via Amazon Bedrock.")

bedrock = load_bedrock()

tab_single, tab_multi, tab_compare, tab_ansible = st.tabs(["Single File", "Multi-File", "Compare", "Ansible"])

# ── Single File ──────────────────────────────────────────────────────────────
with tab_single:
    uploaded_files = st.file_uploader(
        "Upload a .tf file (optional)",
        type=["tf"],
        accept_multiple_files=False,
        key="single_upload",
    )

    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.subheader("Terraform Code")
        if uploaded_files:
            try:
                contents = uploaded_files.read().decode("utf-8")
            except UnicodeDecodeError:
                contents = uploaded_files.read().decode("latin-1")
            initial = contents
            st.caption(f"Loaded: `{uploaded_files.name}`")
        else:
            initial = EXAMPLE_CODE

        code = st.text_area(
            "HCL",
            value=initial,
            height=400,
            label_visibility="collapsed",
            key="single_code",
        )
        review_btn = st.button("Review", type="primary", use_container_width=True, key="single_btn")

    with col2:
        st.subheader("Findings")
        if review_btn and code.strip():
            with st.spinner("Reviewing..."):
                result = review_terraform(code, bedrock=bedrock)
            if result.get("summary"):
                st.info(result["summary"])
            render_findings(result.get("findings", []))
            st.download_button(
                label="Download report (.md)",
                data=findings_to_markdown(result),
                file_name="terraform-review.md",
                mime="text/markdown",
            )
        elif review_btn:
            st.warning("Paste some Terraform code first.")
        else:
            st.markdown("*Click **Review** to analyze the code on the left.*")
            
# ── Ansible ──────────────────────────────────────────────────────────────────
with tab_ansible:
    st.caption(
        "Paste an Ansible playbook or upload a .yml file to get structured "
        "security and best-practice feedback."
    )

    ansible_file = st.file_uploader(
        "Upload a playbook .yml file (optional)",
        type=["yml", "yaml"],
        key="ansible_upload",
    )

    col_a1, col_a2 = st.columns([1, 1], gap="large")

    with col_a1:
        st.subheader("Playbook")
        if ansible_file:
            try:
                ansible_initial = ansible_file.read().decode("utf-8")
            except UnicodeDecodeError:
                ansible_initial = ansible_file.read().decode("latin-1")
            st.caption(f"Loaded: `{ansible_file.name}`")
        else:
            ansible_initial = EXAMPLE_ANSIBLE

        ansible_code = st.text_area(
            "Paste your playbook here",
            value=ansible_initial,
            height=400,
            label_visibility="collapsed",
            key="ansible_code",
        )
        ansible_btn = st.button("Review Playbook", type="primary", use_container_width=True, key="ansible_btn")

    with col_a2:
        st.subheader("Findings")
        if ansible_btn and ansible_code.strip():
            with st.spinner("Reviewing playbook..."):
                ansible_result = review_ansible(ansible_code, bedrock=bedrock)
            if ansible_result.get("summary"):
                st.info(ansible_result["summary"])
            render_findings(ansible_result.get("findings", []))
            st.download_button(
                label="Download report (.md)",
                data=ansible_findings_to_markdown(ansible_result),
                file_name="ansible-review.md",
                mime="text/markdown",
            )
        elif ansible_btn:
            st.warning("Paste a playbook first.")
        else:
            st.markdown("*Click **Review Playbook** to analyze the playbook on the left.*")