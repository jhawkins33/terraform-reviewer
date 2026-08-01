"""
Terraform Reviewer -- Streamlit UI.

Paste Terraform HCL code or upload a .tf file and get structured
security and best-practice feedback powered by Claude via Amazon Bedrock.

Usage:
    streamlit run app.py
"""

import streamlit as st
from src.reviewer import get_bedrock_client, review_terraform

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


@st.cache_resource
def load_bedrock():
    return get_bedrock_client()


st.title("🔍 Terraform Reviewer")
st.caption(
    "Paste your Terraform HCL below or upload a .tf file, then click "
    "Review to get structured security and best-practice feedback "
    "powered by Claude via Amazon Bedrock."
)

bedrock = load_bedrock()

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("Terraform Code")

    uploaded_file = st.file_uploader(
        "Upload a .tf file (optional)",
        type=["tf"],
        help="Upload a Terraform file to populate the editor below.",
    )

    # Determine the initial value for the text area:
    # uploaded file takes priority, otherwise show the example.
    if uploaded_file is not None:
        try:
            file_contents = uploaded_file.read().decode("utf-8")
        except UnicodeDecodeError:
            file_contents = uploaded_file.read().decode("latin-1")
        initial_code = file_contents
        st.caption(f"Loaded: `{uploaded_file.name}` ({len(file_contents)} chars)")
    else:
        initial_code = EXAMPLE_CODE

    code = st.text_area(
        "Paste your HCL here",
        value=initial_code,
        height=400,
        label_visibility="collapsed",
        key=uploaded_file.name if uploaded_file else "default",
    )

    review_btn = st.button("Review", type="primary", use_container_width=True)

with col2:
    st.subheader("Findings")

    if review_btn and code.strip():
        with st.spinner("Reviewing..."):
            result = review_terraform(code, bedrock=bedrock)

        summary = result.get("summary", "")
        findings = result.get("findings", [])

        if summary:
            st.info(summary)

        if not findings:
            st.success("No issues found — looks good!")
        else:
            high = [f for f in findings if f["severity"] == "HIGH"]
            medium = [f for f in findings if f["severity"] == "MEDIUM"]
            low = [f for f in findings if f["severity"] == "LOW"]

            for group, label in [(high, "HIGH"), (medium, "MEDIUM"), (low, "LOW")]:
                if group:
                    st.markdown(f"**{SEVERITY_COLORS[label]} {label}** ({len(group)})")
                    for finding in group:
                        with st.expander(f"{finding['category']} — {finding['title']}"):
                            st.markdown(finding["detail"])

    elif review_btn:
        st.warning("Paste some Terraform code first.")
    else:
        st.markdown("*Click **Review** to analyze the code on the left.*")