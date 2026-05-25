import streamlit as st

from ui.api import api_request, format_api_error
from ui.query_params import set_query_page
from ui.session import set_auth


def render_register_page() -> None:
    st.header("Account")
    st.subheader("Register")

    with st.form("register-form"):
        email = st.text_input("Email", key="register-email")
        password = st.text_input("Password", type="password", key="register-password")
        submitted = st.form_submit_button("Create account")

    if submitted:
        try:
            response = api_request(
                "POST",
                "/v1/auth/register",
                json={"email": email, "password": password},
            )
        except RuntimeError as exc:
            st.error(str(exc))
            return
        if response.ok:
            payload = response.json()
            set_auth(payload["access_token"], payload["user"])
            set_query_page("notes")
            st.rerun()
        else:
            st.error(format_api_error(response, "Registration failed."))

    st.divider()
    if st.button("Already have an account? Sign in"):
        set_query_page("login")
        st.rerun()
