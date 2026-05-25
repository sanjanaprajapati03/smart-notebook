from typing import Any

import streamlit as st


def _normalize_query_value(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, list):
        return value[0] if value else default
    return value or default


def get_query_params() -> dict[str, str]:
    if hasattr(st, "query_params"):
        return {
            key: _normalize_query_value(value, "")
            for key, value in st.query_params.items()
        }
    params = st.experimental_get_query_params()
    return {key: _normalize_query_value(value, "") for key, value in params.items()}


def set_query_params(params: dict[str, str]) -> None:
    normalized = {key: str(value) for key, value in params.items() if value is not None}
    if hasattr(st, "query_params"):
        st.query_params.clear()
        for key, value in normalized.items():
            st.query_params[key] = value
        return
    st.experimental_set_query_params(**normalized)


def get_query_page(default: str) -> str:
    return get_query_params().get("page") or default


def set_query_page(page: str) -> None:
    params = get_query_params()
    params["page"] = page
    set_query_params(params)
