import streamlit as st

from ui.api import api_request, format_api_error
from ui.query_params import set_query_page
from ui.session import set_auth


def render_login_page() -> None:
    st.header("Account")
    st.subheader("Login")

    with st.form("login-form"):
        email = st.text_input("Email", key="login-email")
        password = st.text_input("Password", type="password", key="login-password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        try:
            response = api_request(
                "POST",
                "/v1/auth/login",
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
            st.error(format_api_error(response, "Login failed."))

    st.divider()
    if st.button("Create account"):
        set_query_page("register")
        st.rerun()
