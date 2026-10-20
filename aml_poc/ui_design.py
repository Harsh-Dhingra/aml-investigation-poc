"""Presentation primitives for the bank AML investigation console."""

from html import escape

import streamlit as st


def text(value):
    return escape(str(value))


def badge(label, tone="neutral"):
    return f'<span class="status-badge {text(tone)}">{text(label)}</span>'


def page_header(section, title, description):
    st.html(
        f'<div class="page-heading"><div class="section-label">{text(section)}</div><h1>{text(title)}</h1><p>{text(description)}</p></div>'
    )


def metrics(items):
    cards = "".join(
        f'<div class="summary-card"><div class="summary-label">{text(label)}</div><div class="summary-number {text(tone)}">{text(value)}</div><div class="summary-note">{text(note)}</div></div>'
        for label, value, note, tone in items
    )
    st.html(f'<div class="summary-grid" style="--columns:{len(items)}">{cards}</div>')


def section_heading(title, detail=""):
    st.html(f'<div class="panel-heading"><h3>{text(title)}</h3><span>{text(detail)}</span></div>')


def entity_header(alert, profile=None):
    profile = profile or {}
    name = alert["customer_name"]
    tags = badge(alert["priority"] + " priority", alert["priority"]) + badge(
        alert["signal_status"], "gold" if alert["signal_status"] == "provisional" else "neutral"
    )
    st.html(
        f'<div class="entity-header"><div><div class="section-label">CUSTOMER UNDER REVIEW</div><h2>{text(name)}</h2><div class="entity-meta">{text(alert["customer_id"])}<span>·</span>{text(profile.get("account_id", "Account profile pending"))}<span>·</span>{text(" / ".join(alert["pattern_ids"]))}</div></div><div class="entity-badges">{tags}</div></div>'
    )


def finding_card(index, finding):
    citations = "".join(f'<span class="evidence-chip">{text(key)}</span>' for key in finding["evidence_ids"])
    st.html(
        f'<div class="finding"><div class="finding-label">FINDING {index:02}</div><p>{text(finding["text"])}</p><div class="finding-sources"><span>Supporting evidence</span>{citations}</div></div>'
    )


def detail_rows(items):
    rows = "".join(
        f'<div class="detail-row"><span>{text(label)}</span><strong>{text(value)}</strong></div>'
        for label, value in items
    )
    st.html(f'<div class="detail-list">{rows}</div>')


def note(title, content, tone="neutral"):
    st.html(
        f'<div class="review-note {text(tone)}"><div class="finding-label">{text(title)}</div><p>{text(content)}</p></div>'
    )


def style_queue(frame):
    def priority(value):
        palette = {"HIGH": "#f87171", "MEDIUM": "#fde047", "LOW": "#34d399"}
        return f"color:{palette.get(value, '#d5d9df')}; font-weight:600"

    return frame.style.map(priority, subset=["Priority"]).format({"Transaction value": "${:,.2f}"})
