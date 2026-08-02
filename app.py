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

EXAMPLE_FIXED = """\
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"
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

tab_single, tab_multi, tab_compare = st.tabs(["Single File", "Multi-File", "Compare"])

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
        elif review_btn:
            st.warning("Paste some Terraform code first.")
        else:
            st.markdown("*Click **Review** to analyze the code on the left.*")

# ── Multi-File ───────────────────────────────────────────────────────────────
with tab_multi:
    multi_files = st.file_uploader(
        "Upload .tf files",
        type=["tf"],
        accept_multiple_files=True,
        key="multi_upload",
    )

    if len(multi_files) > 1:
        st.markdown(f"**{len(multi_files)} files uploaded** — reviewing each independently.")
        st.caption("Cross-file references are not visible within each file's review.")

        if st.button("Review All Files", type="primary", key="multi_btn"):
            all_high = all_medium = all_low = 0
            results = {}
            progress = st.progress(0, text="Starting review...")
            for i, f in enumerate(multi_files):
                progress.progress(i / len(multi_files), text=f"Reviewing {f.name}...")
                try:
                    c = f.read().decode("utf-8")
                except UnicodeDecodeError:
                    c = f.read().decode("latin-1")
                result = review_terraform(c, bedrock=bedrock)
                results[f.name] = result
                findings = result.get("findings", [])
                all_high += sum(1 for x in findings if x["severity"] == "HIGH")
                all_medium += sum(1 for x in findings if x["severity"] == "MEDIUM")
                all_low += sum(1 for x in findings if x["severity"] == "LOW")
            progress.progress(1.0, text="Done.")
            st.markdown("---")
            st.markdown(
                f"**Summary across {len(multi_files)} files:** "
                f"{SEVERITY_COLORS['HIGH']} {all_high} HIGH &nbsp; "
                f"{SEVERITY_COLORS['MEDIUM']} {all_medium} MEDIUM &nbsp; "
                f"{SEVERITY_COLORS['LOW']} {all_low} LOW"
            )
            st.markdown("---")
            for filename, result in results.items():
                findings = result.get("findings", [])
                fh = sum(1 for x in findings if x["severity"] == "HIGH")
                fm = sum(1 for x in findings if x["severity"] == "MEDIUM")
                with st.expander(f"`{filename}` — {fh} HIGH, {fm} MEDIUM", expanded=fh > 0):
                    if result.get("summary"):
                        st.info(result["summary"])
                    render_findings(findings)
    elif len(multi_files) == 1:
        st.info("Only one file uploaded — use the Single File tab instead.")

# ── Compare ──────────────────────────────────────────────────────────────────
with tab_compare:
    st.caption(
        "Review original and revised Terraform side-by-side. "
        "See what was fixed, what's new, and what still needs attention."
    )

    col_before, col_after = st.columns([1, 1], gap="large")

    with col_before:
        st.subheader("Before")
        before_file = st.file_uploader("Upload original .tf", type=["tf"], key="before_upload")
        if before_file:
            try:
                before_initial = before_file.read().decode("utf-8")
            except UnicodeDecodeError:
                before_initial = before_file.read().decode("latin-1")
            st.caption(f"Loaded: `{before_file.name}`")
        else:
            before_initial = EXAMPLE_CODE
        before_code = st.text_area("Before HCL", value=before_initial, height=300,
                                   label_visibility="collapsed", key="before_code")

    with col_after:
        st.subheader("After")
        after_file = st.file_uploader("Upload revised .tf", type=["tf"], key="after_upload")
        if after_file:
            try:
                after_initial = after_file.read().decode("utf-8")
            except UnicodeDecodeError:
                after_initial = after_file.read().decode("latin-1")
            st.caption(f"Loaded: `{after_file.name}`")
        else:
            after_initial = EXAMPLE_FIXED
        after_code = st.text_area("After HCL", value=after_initial, height=300,
                                  label_visibility="collapsed", key="after_code")

    compare_btn = st.button("Compare", type="primary", use_container_width=True, key="compare_btn")

    if compare_btn and before_code.strip() and after_code.strip():
        with st.spinner("Reviewing both versions..."):
            before_result = review_terraform(before_code, bedrock=bedrock)
            after_result = review_terraform(after_code, bedrock=bedrock)

        before_findings = before_result.get("findings", [])
        after_findings = after_result.get("findings", [])
        resolved, new, remaining = compare_findings(before_findings, after_findings)

        st.markdown("---")
        col_r, col_n, col_rem = st.columns(3)
        col_r.metric("Resolved", len(resolved), delta=f"-{len(resolved)}", delta_color="normal")
        col_n.metric("New", len(new), delta=f"+{len(new)}" if new else "0", delta_color="inverse")
        col_rem.metric("Remaining", len(remaining))

        if resolved:
            st.markdown("### ✅ Resolved")
            for f in resolved:
                with st.expander(f"{SEVERITY_COLORS[f['severity']]} {f['severity']} — {f['title']}"):
                    st.markdown(f["detail"])

        if new:
            st.markdown("### 🆕 New findings in revised version")
            for f in new:
                with st.expander(f"{SEVERITY_COLORS[f['severity']]} {f['severity']} — {f['title']}"):
                    st.markdown(f["detail"])

        if remaining:
            st.markdown("### ⚠️ Still present")
            for f in remaining:
                with st.expander(f"{SEVERITY_COLORS[f['severity']]} {f['severity']} — {f['title']}"):
                    st.markdown(f["detail"])

        if not resolved and not new and not remaining:
            st.success("Both versions look identical in terms of findings.")

    elif compare_btn:
        st.warning("Paste code in both panels before comparing.")