import os
import secrets
import time
from typing import Any

import streamlit as st

from .query_params import get_query_params, set_query_params

SESSION_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")) * 60
_SESSION_CACHE: dict[str, dict[str, Any]] = {}


def ensure_session_id() -> str:
    params = get_query_params()
    session_id = params.get("sid")
    if not session_id:
        session_id = secrets.token_urlsafe(16)
        params["sid"] = session_id
        set_query_params(params)
        st.rerun()
    st.session_state["sid"] = session_id
    return session_id


def _get_record(session_id: str) -> dict[str, Any] | None:
    record = _SESSION_CACHE.get(session_id)
    if not record:
        return None
    if record["expires_at"] <= time.time():
        _SESSION_CACHE.pop(session_id, None)
        return None
    return record


def hydrate_auth_from_store() -> None:
    expires_at = st.session_state.get("auth_expires_at")
    if expires_at and expires_at <= time.time():
        clear_auth()
        return
    if st.session_state.get("access_token"):
        return
    session_id = st.session_state.get("sid")
    if not session_id:
        return
    record = _get_record(session_id)
    if not record:
        return
    st.session_state["access_token"] = record["access_token"]
    st.session_state["user"] = record["user"]
    st.session_state["auth_expires_at"] = record["expires_at"]


def set_auth(access_token: str, user: dict) -> None:
    expires_at = time.time() + SESSION_TTL_SECONDS
    st.session_state["access_token"] = access_token
    st.session_state["user"] = user
    st.session_state["auth_expires_at"] = expires_at
    session_id = st.session_state.get("sid")
    if not session_id:
        return
    _SESSION_CACHE[session_id] = {
        "access_token": access_token,
        "user": user,
        "expires_at": expires_at,
    }


def clear_auth() -> None:
    st.session_state.pop("access_token", None)
    st.session_state.pop("user", None)
    st.session_state.pop("auth_expires_at", None)
    session_id = st.session_state.get("sid")
    if session_id:
        _SESSION_CACHE.pop(session_id, None)
