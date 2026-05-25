import os
import sys

import streamlit as st

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ui.query_params import get_query_page, set_query_page
from ui.session import clear_auth, ensure_session_id, hydrate_auth_from_store
from ui.views.discovery import render_discover_page
from ui.views.login import render_login_page
from ui.views.notes import render_notes_page
from ui.views.register import render_register_page


def main() -> None:
    st.set_page_config(page_title="Second Brain", layout="wide")
    ensure_session_id()
    hydrate_auth_from_store()

    is_authed = bool(st.session_state.get("access_token"))
    default_page = "notes" if is_authed else "login"
    current_page = get_query_page(default_page)

    if is_authed and current_page in {"login", "register"}:
        set_query_page("notes")
        st.rerun()

    if not is_authed and current_page not in {"login", "register"}:
        set_query_page("login")
        st.rerun()

    if is_authed:
        st.sidebar.title("Second Brain")
        page_options = {
            "notes": "Notes",
            "discover": "Discover",
        }
        if current_page not in page_options:
            current_page = "notes"

        selection = st.sidebar.radio(
            "Navigate",
            list(page_options.keys()),
            format_func=lambda key: page_options[key],
            index=list(page_options.keys()).index(current_page),
        )

        if selection != current_page:
            set_query_page(selection)
            st.rerun()

        if st.sidebar.button("Log out"):
            clear_auth()
            set_query_page("login")
            st.rerun()

        if selection == "notes":
            render_notes_page()
        else:
            render_discover_page()
    else:
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] { display: none; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        if current_page == "register":
            render_register_page()
        else:
            render_login_page()


if __name__ == "__main__":
    main()
