"""Small shared Streamlit presentation helpers."""

import streamlit as st


def render_placeholder(title: str, description: str, next_step: str) -> None:
    st.title(title)
    st.caption("FINWISE AI · WORKSPACE")
    st.write(description)
    st.info("This section is a UI scaffold. No model or recommendation is being presented here.")
    st.subheader("Module status")
    st.write(next_step)
