"""Streamlit demo: extraction review, findings dashboard, policy chat."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("LEDGERLENS_API_URL", "http://localhost:8070")

st.set_page_config(page_title="ledgerlens", page_icon="🧾", layout="wide")
st.title("🧾 ledgerlens")
st.caption("Invoice intelligence: extraction, bookkeeping validation, policy Q&A")


def _ok() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


if not _ok():
    st.error(f"API not reachable at {API_URL}. Start it with `make api`.")
    st.stop()

tab_ledger, tab_upload, tab_policy = st.tabs(["Ledger & findings", "Extract a PDF", "Policy chat"])

with tab_ledger:
    r = httpx.get(f"{API_URL}/ledger", params={"limit": 200}, timeout=30)
    if r.status_code != 200:
        st.warning(r.json().get("detail", r.text))
    else:
        df = pd.DataFrame(r.json())
        c1, c2, c3 = st.columns(3)
        c1.metric("Invoices", len(df))
        c2.metric("With findings", int((df["n_findings"] > 0).sum()))
        c3.metric("Total value", f"{df['total'].fillna(0).sum():,.0f}")
        st.dataframe(
            df[
                [
                    "file",
                    "invoice_no",
                    "vendor",
                    "invoice_date",
                    "total",
                    "n_findings",
                    "max_severity",
                    "review_fields",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Findings detail")
        fr = httpx.get(f"{API_URL}/findings", timeout=30)
        for item in fr.json() if fr.status_code == 200 else []:
            with st.expander(f"{item['file']} — {item['invoice_no']} ({item['vendor']})"):
                for f in item["findings"]:
                    icon = "🛑" if f["severity"] == "error" else "⚠️"
                    st.markdown(f"{icon} **{f['rule']}** — {f['message']}")

with tab_upload:
    uploaded = st.file_uploader("Invoice PDF", type="pdf")
    if uploaded is not None and st.button("Audit invoice", type="primary"):
        r = httpx.post(
            f"{API_URL}/audit",
            files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
            timeout=120,
        )
        if r.status_code != 200:
            st.error(r.json().get("detail", r.text))
        else:
            body = r.json()
            rows = [
                {
                    "field": k,
                    "value": v["value"],
                    "confidence": v["confidence"],
                    "source": v["source"],
                }
                for k, v in body["fields"].items()
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            if body["review_fields"]:
                st.warning("Needs a human look: " + ", ".join(body["review_fields"]))
            if body["findings"]:
                for f in body["findings"]:
                    icon = "🛑" if f["severity"] == "error" else "⚠️"
                    st.markdown(f"{icon} **{f['rule']}** — {f['message']}")
                    policy = f.get("policy")
                    if policy:
                        st.info(f"**[{policy['doc']} / {policy['section']}]** {policy['excerpt']}")
                    else:
                        st.caption("No policy clause matched this finding.")
            else:
                st.success("No validation findings.")
            st.caption(
                "Stages: "
                + " · ".join(
                    f"{s['stage']} {s['ms']:.0f} ms ({s['status']})" for s in body["stages"]
                )
            )

with tab_policy:
    provider = st.radio("Provider", ["ollama", "claude", "fake"], horizontal=True)
    question = st.text_input(
        "Ask the policy assistant",
        placeholder="Can we accept an invoice with 90-day payment terms?",
    )
    if question and len(question) >= 5:
        with st.spinner(f"Asking {provider}…"):
            r = httpx.post(
                f"{API_URL}/ask", json={"question": question, "provider": provider}, timeout=300
            )
        if r.status_code != 200:
            st.error(r.json().get("detail", r.text))
        else:
            body = r.json()
            if body.get("degraded"):
                st.warning(
                    f"No model answer ({body.get('reason', 'provider unavailable')}); "
                    "showing the retrieved policy excerpts instead."
                )
            else:
                st.markdown(body["answer"])
            with st.expander(
                f"Sources ({len(body['sources'])})", expanded=body.get("degraded", False)
            ):
                for s in body["sources"]:
                    st.markdown(f"**[{s['doc']} / {s['section']}]** {s['preview']}")
