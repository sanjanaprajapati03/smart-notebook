import json

import requests
import streamlit as st

from ui.api import api_request, format_api_error


def _split_title(content: str) -> str:
    if not content:
        return "Untitled"
    first_line = content.splitlines()[0].strip()
    return first_line or "Untitled"


def _load_notes(token: str, limit: int = 200) -> list[dict]:
    cache_key = "discovery_notes_cache"
    if st.session_state.get("discovery_notes_limit") != limit:
        st.session_state.pop(cache_key, None)
        st.session_state["discovery_notes_limit"] = limit

    if cache_key not in st.session_state:
        with st.spinner("Loading notes..."):
            try:
                response = api_request(
                    "GET",
                    "/v1/notes",
                    token=token,
                    params={"limit": limit},
                )
            except RuntimeError as exc:
                st.error(str(exc))
                return []
            if response.ok:
                st.session_state[cache_key] = response.json()
            else:
                st.error(format_api_error(response, "Failed to load notes."))
                return []

    return st.session_state.get(cache_key, [])


def stream_discovery(
    limit: int,
    min_score: float,
    max_chunks: int,
    token: str,
    note_ids: list[str],
) -> str:
    response = api_request(
        "GET",
        "/v1/notes/discover",
        token=token,
        params={
            "limit": limit,
            "min_score": min_score,
            "max_chunks": max_chunks,
            "note_ids": note_ids,
        },
        headers={"Accept": "text/event-stream"},
        stream=True,
    )
    response.raise_for_status()

    output = ""
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line.replace("data: ", "", 1)
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            continue
        output += message.get("text", "")
    return output


def render_discover_page() -> None:
    st.header("Discover relationships")
    token = st.session_state.get("access_token")
    if not token:
        st.info("Sign in to discover relationships.")
        return

    if st.button("Refresh notes list"):
        st.session_state.pop("discovery_notes_cache", None)
    notes = _load_notes(token)
    if not notes:
        st.info("No notes available yet.")
        return

    note_titles = {note.get("id"): _split_title(note.get("content", "")) for note in notes}
    note_options = [note.get("id") for note in notes if note.get("id")]

    select_all = st.checkbox("Select all notes", value=False, key="discover_select_all")
    if select_all:
        st.session_state["discover_selected_notes"] = note_options
    if "discover_selected_notes" not in st.session_state:
        st.session_state["discover_selected_notes"] = []

    selected_notes = st.multiselect(
        "Notes to analyze",
        note_options,
        format_func=lambda note_id: note_titles.get(note_id, note_id),
        key="discover_selected_notes",
    )

    if st.button("Analyze notes"):
        if not selected_notes:
            st.warning("Select at least one note to analyze.")
            return
        placeholder = st.empty()
        try:
            with st.spinner("Analyzing notes..."):
                text = stream_discovery(10, 0.78, 200, token, selected_notes)
            placeholder.markdown(text)
        except (requests.RequestException, RuntimeError) as exc:
            placeholder.error(str(exc))
