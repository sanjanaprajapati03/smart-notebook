import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://0.0.0.0:8000").rstrip("/")


def get_api_base_url() -> str:
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = DEFAULT_API_BASE_URL
    return str(st.session_state["api_base_url"]).rstrip("/")


def api_request(
    method: str, path: str, token: str | None = None, **kwargs: object
) -> requests.Response:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base_url = get_api_base_url()
    url = f"{base_url}{path}"
    timeout = kwargs.pop("timeout", 30)
    try:
        return requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"API is not reachable at {base_url}. Start the FastAPI server or update the API URL."
        ) from exc


def check_api_health() -> tuple[bool, str]:
    try:
        response = api_request("GET", "/health", timeout=3)
    except RuntimeError as exc:
        return False, str(exc)

    if response.ok:
        return True, "API is reachable."

    return False, f"API returned HTTP {response.status_code}."


def format_api_error(response: requests.Response, fallback: str) -> str:
    status = response.status_code
    try:
        payload = response.json()
    except ValueError:
        body = response.text.strip()
        if body:
            return f"{fallback} (HTTP {status}): {body}"
        return f"{fallback} (HTTP {status})."

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            return detail

    return f"{fallback} (HTTP {status})."


def render_api_connection_panel() -> None:
    current_url = get_api_base_url()
    new_url = st.text_input("API base URL", value=current_url)
    if new_url and new_url.rstrip("/") != current_url:
        st.session_state["api_base_url"] = new_url.rstrip("/")
        current_url = st.session_state["api_base_url"]

    ok, message = check_api_health()
    if ok:
        st.success(message)
    else:
        st.warning(message)
