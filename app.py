"""
Terraform Reviewer -- Streamlit UI.

Paste Terraform HCL code, upload a single .tf file, or upload
multiple .tf files for a full project review. Get structured
security and best-practice feedback powered by Claude via Bedrock.

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


def render_findings(findings):
    """Render a severity-grouped findings panel."""
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


st.title("🔍 Terraform Reviewer")
st.caption(
    "Paste HCL, upload a single .tf file, or upload multiple .tf files "
    "for a full project review. Powered by Claude via Amazon Bedrock."
)

bedrock = load_bedrock()

uploaded_files = st.file_uploader(
    "Upload .tf file(s)",
    type=["tf"],
    accept_multiple_files=True,
    help="Upload one or more Terraform files. Each file is reviewed independently.",
)

# --- Multi-file mode ---
if len(uploaded_files) > 1:
    st.markdown(f"**{len(uploaded_files)} files uploaded** — reviewing each independently.")
    st.caption(
        "Note: files are reviewed independently, so cross-file references "
        "(e.g. a resource defined in one file and used in another) are not "
        "visible within each file's review."
    )

    if st.button("Review All Files", type="primary"):
        all_high = all_medium = all_low = 0
        results = {}

        progress = st.progress(0, text="Starting review...")
        for i, f in enumerate(uploaded_files):
            progress.progress((i) / len(uploaded_files), text=f"Reviewing {f.name}...")
            try:
                code = f.read().decode("utf-8")
            except UnicodeDecodeError:
                code = f.read().decode("latin-1")
            result = review_terraform(code, bedrock=bedrock)
            results[f.name] = result
            findings = result.get("findings", [])
            all_high += sum(1 for x in findings if x["severity"] == "HIGH")
            all_medium += sum(1 for x in findings if x["severity"] == "MEDIUM")
            all_low += sum(1 for x in findings if x["severity"] == "LOW")

        progress.progress(1.0, text="Done.")

        st.markdown("---")
        st.markdown(
            f"**Summary across {len(uploaded_files)} files:** "
            f"{SEVERITY_COLORS['HIGH']} {all_high} HIGH &nbsp; "
            f"{SEVERITY_COLORS['MEDIUM']} {all_medium} MEDIUM &nbsp; "
            f"{SEVERITY_COLORS['LOW']} {all_low} LOW"
        )
        st.markdown("---")

        for filename, result in results.items():
            findings = result.get("findings", [])
            file_high = sum(1 for x in findings if x["severity"] == "HIGH")
            file_medium = sum(1 for x in findings if x["severity"] == "MEDIUM")
            header = f"`{filename}` — {file_high} HIGH, {file_medium} MEDIUM"
            with st.expander(header, expanded=file_high > 0):
                summary = result.get("summary", "")
                if summary:
                    st.info(summary)
                render_findings(findings)

# --- Single file or paste mode ---
else:
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("Terraform Code")

        if uploaded_files:
            f = uploaded_files[0]
            try:
                file_contents = f.read().decode("utf-8")
            except UnicodeDecodeError:
                file_contents = f.read().decode("latin-1")
            initial_code = file_contents
            st.caption(f"Loaded: `{f.name}` ({len(file_contents)} chars)")
        else:
            initial_code = EXAMPLE_CODE

        code = st.text_area(
            "Paste your HCL here",
            value=initial_code,
            height=400,
            label_visibility="collapsed",
            key=uploaded_files[0].name if uploaded_files else "default",
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
            render_findings(findings)

        elif review_btn:
            st.warning("Paste some Terraform code first.")
        else:
            st.markdown("*Click **Review** to analyze the code on the left.*")