from __future__ import annotations

import asyncio

import altair as alt
import pandas as pd
import streamlit as st

from belvo_finance_agent.agent import build_agent
from belvo_finance_agent.config import get_settings
from belvo_finance_agent.logging_config import configure_logging
from belvo_finance_agent.mcp_client import MCPError
from belvo_finance_agent.models import ChartSpec, FinancialAnswer
from belvo_finance_agent.streaming import enable_streaming, stream_text


configure_logging()


def render_chart(chart: ChartSpec | None) -> None:
    if not chart or not chart.data:
        return
    first_row = chart.data[0]
    x_column = next((key for key in first_row if key != "Total"), None)
    if not x_column:
        return
    st.caption(chart.title)
    if chart.chart_type == "pie":
        df = pd.DataFrame(chart.data).sort_values("Total", ascending=False)
        pie = (
            alt.Chart(df)
            .mark_arc()
            .encode(
                theta=alt.Theta("Total:Q", title=chart.y_label),
                color=alt.Color(f"{x_column}:N", title=chart.x_label),
                tooltip=[x_column, alt.Tooltip("Total:Q", format=",.2f")],
            )
            .properties(title=chart.title)
        )
        st.altair_chart(pie, use_container_width=True)
    elif chart.chart_type == "bar":
        st.bar_chart(chart.data, x=x_column, y="Total")


def render_evidence(answer: FinancialAnswer) -> None:
    with st.expander("Evidence & assumptions"):
        st.markdown(
            "\n".join(
                [
                    f"- Workflow: `{answer.workflow}`",
                    f"- Tools used: {', '.join(answer.tools_used) if answer.tools_used else 'none'}",
                    f"- Filters: `{answer.filters}`",
                    f"- Loaded skills: {', '.join(answer.metadata.get('loaded_skills', [])) or 'none'}",
                    f"- Matched transactions: `{answer.metadata.get('matches', answer.metadata.get('transactions_after_filtering', 'n/a'))}`",
                ]
            )
        )
        st.json(answer.model_dump(mode="json"))

st.set_page_config(page_title="Belvo Financial Specialist Agent", page_icon="BRL", layout="centered")
st.title("Belvo Financial Specialist Agent")
st.caption("Read-only answers grounded in the local Open Finance MCP dataset.")

debug = st.toggle("Show evidence and filters", value=False)
settings = get_settings()

sample_questions = [
    "What's my current balance across all my accounts?",
    "How much I spent today?",
    "How much did I spend last week?",
    "How much did I spend in May 2026?",
    "when I last did a payment",
    "what was my biggest expense on May",
    "show me all my expenses in May",
    "qual foi meu maior gasto em maio",
    "show me only PIX transactions",
    "how much did I send by PIX?",
    "show me all credit card transactions",
    "show me all Nubank transactions",
    "show me Itau checking expenses",
    "How much did I spend on food in the last 30 days?",
    "Did my salary come in this month?",
    "Show me transactions over R$ 500 in the last 90 days.",
    "What's my biggest recurring expense?",
]

selected = st.selectbox("Try a representative question", [""] + sample_questions)
question = st.chat_input("Ask about the user's finances")
question = question or selected

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Querying MCP and calculating..."):
            try:
                answer = asyncio.run(build_agent().answer(question))
                if enable_streaming(configured=settings.enable_streaming):
                    st.write_stream(stream_text(answer.answer))
                else:
                    st.markdown(answer.answer)
                render_chart(answer.chart)
                if debug:
                    render_evidence(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer.answer})
            except MCPError as exc:
                message = str(exc)
                st.error(message)
                st.session_state.messages.append({"role": "assistant", "content": message})
