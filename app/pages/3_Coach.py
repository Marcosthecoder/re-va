import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from app.common import disclaimer_banner, esc, load_profile, require_login, session
from coach import quiz as quiz_mod
from coach.chat import ask
from db.repository import get_deal, list_deals, load_property_input
from llm.client import LLMNotConfigured
from reports.report_builder import build_report
from underwriting.pipeline import analyze_deal

st.set_page_config(page_title="RE-VA — Coach", layout="wide")

s = session()
user = require_login(s)

st.title("Coach")
disclaimer_banner()

deals = list_deals(s, user.id)
options = {"No specific deal": None, **{f"{d.deal_name} ({d.address})": d.id for d in deals}}
choice = st.selectbox("Use a deal as the worked example?", options=list(options))
deal_id = options[choice]

report = None
if deal_id is not None:
    deal_row = get_deal(s, deal_id, user.id)
    profile = load_profile(s, user)
    deal = load_property_input(deal_row)
    full = analyze_deal(deal, profile)
    report = build_report(deal, full.analysis, full.verdict, full.hh_bundle)

tab_chat, tab_quiz = st.tabs(["Ask the coach", "Quiz"])

with tab_chat:
    st.session_state.setdefault("coach_history", [])
    for q, a in st.session_state["coach_history"]:
        st.chat_message("user").write(q)
        st.chat_message("assistant").write(a)

    question = st.chat_input("Ask about NOI, cap rate, DSCR, NNN leases, due diligence, or anything about this deal...")
    if question:
        st.chat_message("user").write(esc(question))
        try:
            answer = ask(question, report=report, history=st.session_state["coach_history"], session=s, deal_id=deal_id)
        except LLMNotConfigured as e:
            answer = None
            st.chat_message("assistant").warning(str(e))
        if answer:
            st.chat_message("assistant").write(esc(answer))
            st.session_state["coach_history"].append((question, answer))

    if st.session_state["coach_history"] and st.button("Clear conversation"):
        st.session_state["coach_history"] = []
        st.rerun()

with tab_quiz:
    topic = st.selectbox("Topic", ["All"] + quiz_mod.topics())
    questions = quiz_mod.get_quiz(None if topic == "All" else topic)

    st.session_state.setdefault("quiz_index", 0)
    st.session_state.setdefault("quiz_score", 0)
    st.session_state.setdefault("quiz_answered", False)

    if st.button("Start / restart quiz"):
        st.session_state["quiz_index"] = 0
        st.session_state["quiz_score"] = 0
        st.session_state["quiz_answered"] = False
        st.rerun()

    idx = st.session_state["quiz_index"]
    if idx < len(questions):
        q = questions[idx]
        st.write(f"**Q{idx + 1}/{len(questions)} ({q.topic}): {q.question}**")
        selected = st.radio("Choose one:", q.choices, key=f"quiz_choice_{idx}", index=None)

        if not st.session_state["quiz_answered"]:
            if st.button("Submit answer") and selected is not None:
                st.session_state["quiz_answered"] = True
                if quiz_mod.check_answer(q, q.choices.index(selected)):
                    st.session_state["quiz_score"] += 1
                st.rerun()
        else:
            correct = quiz_mod.check_answer(q, q.choices.index(selected)) if selected else False
            (st.success if correct else st.error)("Correct!" if correct else f"Not quite. Correct answer: {q.choices[q.correct_index]}")
            st.caption(q.explanation)
            if st.button("Next question"):
                st.session_state["quiz_index"] += 1
                st.session_state["quiz_answered"] = False
                st.rerun()
    else:
        st.success(f"Quiz complete: {st.session_state['quiz_score']} / {len(questions)}")
