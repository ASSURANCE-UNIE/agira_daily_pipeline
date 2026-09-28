"""Standalone Streamlit UI for inspecting AGIRA response JSON files (read-only)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import streamlit as st

from model import (
    as_list,
    contract_overview,
    criteria_items,
    criteria_summary,
    display_value,
    group_contracts,
    history_files,
    matching_contracts,
    parse_response,
    returned_contract_number,
    returned_records,
    segment_code,
    summary_counts,
)


st.set_page_config(
    page_title="AGIRA Contract Viewer",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .stApp { background: #f5f7fa; color: #17212b; }
      [data-testid="stSidebar"] { background: #101923; }
      [data-testid="stSidebar"] * { color: #f4f7fa; }
      [data-testid="stSidebar"] input { color: #17212b; }
      [data-testid="stMetric"] {
        background: white; border: 1px solid #e4e9ef; border-radius: 14px;
        padding: 14px 16px; box-shadow: 0 5px 18px rgba(17, 32, 48, .04);
      }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background: white; border-color: #e2e8ef; border-radius: 14px;
        box-shadow: 0 5px 18px rgba(17, 32, 48, .035);
      }
      .eyebrow { color: #678; font-size: .76rem; letter-spacing: .12em;
        text-transform: uppercase; font-weight: 700; margin-bottom: .35rem; }
      .contract-title { font-size: 2rem; line-height: 1.15; font-weight: 730; margin: 0; }
      .muted { color: #667788; }
      .badge { display: inline-block; padding: .2rem .58rem; border-radius: 999px;
        font-size: .75rem; font-weight: 700; margin-left: .35rem; }
      .badge-ok { color: #087a55; background: #e8f8f1; }
      .badge-no { color: #6b7580; background: #edf0f3; }
      .criteria { color: #506070; font-size: .92rem; line-height: 1.55; }
      .section-rule { height: 1px; background: #e8edf2; margin: .45rem 0 1rem; }
      h1, h2, h3 { color: #16222e; }
    </style>
    """,
    unsafe_allow_html=True,
)


HISTORY_ROOT = Path(__file__).resolve().parent.parent / "data" / "history" / "interrogations" / "resp"


@st.cache_data(show_spinner=False)
def load_history_file(path: str, modified: float) -> dict[str, Any]:
    # `modified` is only part of the cache key, so an updated file is re-read.
    return parse_response(Path(path).read_bytes())


def read_sources(uploaded_files: list[Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return (display name, parsed document) for RESP history files, then uploads."""
    sources: list[tuple[str, dict[str, Any]]] = []
    candidates = [
        (f"{path.parent.name} · {path.name}", lambda path=path: load_history_file(str(path), path.stat().st_mtime))
        for path in history_files(HISTORY_ROOT)
    ] + [
        (f"Upload · {uploaded.name}", lambda uploaded=uploaded: parse_response(uploaded.getvalue()))
        for uploaded in uploaded_files
    ]
    for label, load in candidates:
        try:
            sources.append((label, load()))
        except ValueError as exc:
            st.sidebar.warning(f"Skipped {label}: {exc}")
    return sources


def show_pairs(items: list[tuple[str, str]]) -> None:
    if not items:
        st.caption("No populated fields.")
        return
    st.dataframe(
        [{"Field": label, "Value": value} for label, value in items],
        hide_index=True,
        width="stretch",
        column_config={"Field": st.column_config.TextColumn(width="medium")},
    )


def render_record(record: dict[str, Any], record_number: int) -> None:
    contract = record.get("contract") or {}
    identification = record.get("identification") or {}
    termination = record.get("termination") or {}
    vehicle = record.get("vehicle") or {}
    company = contract.get("company") or identification.get("company") or {}

    st.markdown(f"#### Returned record {record_number}")
    a, b, c, d = st.columns(4)
    a.metric("Contract", returned_contract_number(record))
    b.metric("Insurer", display_value(company.get("company_code")))
    c.metric("Effective date", display_value(contract.get("effective_date")))
    d.metric("Bonus / malus", display_value(contract.get("bonus_malus_coefficient")))

    info_tab, people_tab, claims_tab, raw_tab = st.tabs(
        ["Contract & vehicle", "People", "Claims", "Raw record"]
    )
    with info_tab:
        left, right = st.columns(2)
        with left:
            st.markdown("**Contract**")
            show_pairs(
                [
                    ("Company record ID", display_value(identification.get("company_record_identifier"))),
                    ("Country code", display_value(company.get("country_code"))),
                    ("Company code", display_value(company.get("company_code"))),
                    ("Contract number", display_value(contract.get("contract_number"))),
                    ("Effective date", display_value(contract.get("effective_date"))),
                    ("Bonus / malus", display_value(contract.get("bonus_malus_coefficient"))),
                    ("Termination date", display_value(termination.get("termination_date"))),
                    ("Termination reason", display_value(termination.get("reason_code"))),
                ]
            )
        with right:
            st.markdown("**Vehicle**")
            show_pairs(
                [
                    ("Registration", display_value(vehicle.get("registration_number"))),
                    ("Category", display_value(vehicle.get("category_code"))),
                    ("Manufacturer", display_value(vehicle.get("manufacturer_code"))),
                    ("Type mine", display_value(vehicle.get("type_mine"))),
                    ("Serial number", display_value(vehicle.get("serial_number"))),
                ]
            )
    with people_tab:
        people = as_list(record.get("persons"))
        if people:
            st.dataframe(
                [
                    {
                        "Role": person.get("role") or "—",
                        "Name": person.get("name_or_company_name") or "—",
                        "First name": person.get("first_name") or "—",
                        "Birth date": display_value(person.get("birth_date")),
                        "Licence date": display_value(person.get("driving_licence_date")),
                        "Address": ", ".join(as_list(person.get("address_lines"))) or "—",
                        "Postal code": person.get("postal_code") or "—",
                        "City": person.get("city") or "—",
                    }
                    for person in people
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No person was returned.")
    with claims_tab:
        claims = as_list(record.get("claims"))
        if claims:
            st.dataframe(
                [
                    {
                        "Claim number": claim.get("claim_number") or "—",
                        "Date": display_value(claim.get("claim_date")),
                        "Nature": claim.get("nature_code") or "—",
                        "Guarantee": claim.get("guarantee_code") or "—",
                        "Responsibility": (
                            f"{claim.get('responsibility_percent')}%"
                            if claim.get("responsibility_percent") is not None
                            else "—"
                        ),
                        "Driver": " ".join(
                            filter(None, [claim.get("driver_first_name"), claim.get("driver_last_name")])
                        )
                        or "—",
                    }
                    for claim in claims
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No claims were returned.")
    with raw_tab:
        st.json(record, expanded=False)


def render_contract(number: str, conversations: list[dict[str, Any]]) -> None:
    records = returned_records(conversations)
    matched_count = sum(item.get("status") == "matched" for item in conversations)
    st.markdown('<div class="eyebrow">Submitted contract</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="contract-title">{html.escape(number)}'
        f'<span class="badge badge-ok">{matched_count} matched</span>'
        f'<span class="badge badge-no">{len(conversations) - matched_count} no match</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"{len(conversations)} segments sent · {len(records)} returned record(s)")

    stream_rows = []
    for conversation in conversations:
        conversation_records = as_list(conversation.get("records"))
        reasons = as_list(conversation.get("match_reasons"))
        stream_rows.append(
            {
                "Segment": segment_code(conversation),
                "Criteria sent": criteria_summary(conversation),
                "Result": "Matched" if conversation.get("status") == "matched" else "No match",
                "Match reason": ", ".join(
                    str(reason.get("match_label") or reason.get("match_code") or "")
                    for reason in reasons
                    if isinstance(reason, dict)
                )
                or "—",
                "Returned contract": ", ".join(
                    returned_contract_number(record)
                    for record in conversation_records
                    if isinstance(record, dict)
                )
                or "—",
            }
        )

    st.markdown("### Segment stream")
    st.dataframe(
        stream_rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Segment": st.column_config.TextColumn(width="small"),
            "Criteria sent": st.column_config.TextColumn(width="large"),
            "Result": st.column_config.TextColumn(width="small"),
        },
    )

    selected_index = st.selectbox(
        "Inspect a segment",
        options=range(len(conversations)),
        format_func=lambda index: (
            f"{segment_code(conversations[index])} — "
            f"{'Matched' if conversations[index].get('status') == 'matched' else 'No match'}"
        ),
        key=f"segment-{number}",
    )
    selected = conversations[selected_index]
    left, right = st.columns([1, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown(f"#### {segment_code(selected)} · What was sent")
            st.caption(selected.get("query_id") or "No query ID")
            show_pairs(criteria_items(selected))
            query = selected.get("query") or {}
            protocol = query.get("protocol") or {}
            with st.expander("Transmission details"):
                show_pairs(
                    [
                        ("Emitted at", display_value(query.get("emitted_at_raw"))),
                        ("Message", display_value(protocol.get("message_code"))),
                        ("Layout", display_value(protocol.get("layout"))),
                        ("Line", display_value(protocol.get("line_number"))),
                    ]
                )
    with right:
        with st.container(border=True):
            status = selected.get("status")
            if status == "matched":
                st.markdown("#### ✅ AGIRA result · Match")
                reasons = as_list(selected.get("match_reasons"))
                if reasons:
                    for reason in reasons:
                        if isinstance(reason, dict):
                            st.success(reason.get("match_label") or f"Match code {reason.get('match_code')}")
                selected_records = as_list(selected.get("records"))
                st.markdown(
                    f"**{len(selected_records)} record(s)** returned for this segment. "
                    "The full details are shown below."
                )
            else:
                st.markdown("#### — AGIRA result · No match")
                st.info("This segment returned no matching record.")
            errors = as_list(selected.get("errors"))
            if errors:
                st.error(" · ".join(display_value(error) for error in errors))

    selected_records = [item for item in as_list(selected.get("records")) if isinstance(item, dict)]
    for index, record in enumerate(selected_records, start=1):
        with st.container(border=True):
            render_record(record, index)

    with st.expander("Raw contract conversations"):
        st.json(conversations, expanded=False)


with st.sidebar:
    st.markdown("## AGIRA viewer")
    st.caption("Local, read-only contract response viewer")
    police = st.text_input("Numéro de police", placeholder="e.g. AXS002072").strip()
    uploaded = st.file_uploader(
        "Drop response JSON files here",
        type=["json"],
        accept_multiple_files=True,
        help="Files stay in memory for this session and are not copied or persisted.",
    )
    st.caption("RESP history loads automatically · uploads are not saved")

sources = read_sources(uploaded or [])
if police:
    sources = [source for source in sources if matching_contracts(group_contracts(source[1]), police)]
if not sources:
    st.title("AGIRA Contract Viewer")
    if police:
        st.info(f"No RESP file contains a numéro de police matching “{police}”.")
    else:
        st.info(f"No RESP history found in {HISTORY_ROOT}. Drag a response JSON into the sidebar.")
    st.stop()

with st.sidebar:
    if police:
        st.caption(f"“{police}” found in {len(sources)} file(s)")
    source_index = st.selectbox(
        "File to inspect",
        options=range(len(sources)),
        format_func=lambda index: sources[index][0],
    )

source_label, document = sources[source_index]
grouped = group_contracts(document)
counts = summary_counts(grouped)

with st.sidebar:
    st.divider()
    match_filter = st.radio("Show", ["All", "With a match", "Without a match"], index=0)
    st.download_button(
        "Download current JSON",
        data=json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=source_label.split(" · ", 1)[-1],
        mime="application/json",
        width="stretch",
    )

filtered = []
for number in matching_contracts(grouped, police):
    has_match = any(item.get("status") == "matched" for item in grouped[number])
    if match_filter == "With a match" and not has_match:
        continue
    if match_filter == "Without a match" and has_match:
        continue
    filtered.append(number)

st.markdown('<div class="eyebrow">Response file</div>', unsafe_allow_html=True)
st.title("Contract response viewer")
st.caption(document.get("source_filename") or source_label)

metric_cols = st.columns(5)
metric_cols[0].metric("Contracts", counts["contracts"])
metric_cols[1].metric("Segments sent", counts["segments"])
metric_cols[2].metric("Matched segments", counts["matched"])
metric_cols[3].metric("No match", counts["no_match"])
metric_cols[4].metric("Returned records", counts["records"])

overview_tab, contract_tab, file_tab = st.tabs(["Overview", "Contract by contract", "File details"])
with overview_tab:
    st.markdown("### All submitted contracts")
    overview = [row for row in contract_overview(grouped) if row["Submitted contract"] in filtered]
    if overview:
        st.dataframe(overview, hide_index=True, width="stretch")
    else:
        st.info("No contract matches the current filters.")

with contract_tab:
    if filtered:
        selected_contract = st.selectbox("Contract", filtered, key="contract-picker")
        st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)
        render_contract(selected_contract, grouped[selected_contract])
    else:
        st.info("No contract matches the current filters.")

with file_tab:
    summary = document.get("summary") or {}
    left, right = st.columns(2)
    with left:
        st.markdown("### Parse summary")
        show_pairs([(key.replace("_", " ").title(), display_value(value)) for key, value in summary.items()])
    with right:
        st.markdown("### Source")
        show_pairs(
            [
                ("Document type", display_value(document.get("document_type"))),
                ("Source filename", display_value(document.get("source_filename"))),
                ("Encoding", display_value(document.get("encoding"))),
                ("Viewer source", source_label),
            ]
        )
    with st.expander("Raw file JSON"):
        st.json(document, expanded=False)
