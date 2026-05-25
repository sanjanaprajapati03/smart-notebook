import streamlit as st

from ui.api import api_request, format_api_error


def _split_title_content(text: str) -> tuple[str, str]:
    if not text:
        return "Untitled", ""
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    if not title:
        title = "Untitled"
    body = "\n".join(lines[1:]).lstrip()
    return title, body


def _render_notes_list(token: str) -> None:
    limit = st.slider("Max notes", min_value=1, max_value=200, value=50, step=1)
    if st.button("Refresh list"):
        st.session_state.pop("notes_list_cache", None)

    if st.session_state.get("notes_list_limit") != limit:
        st.session_state.pop("notes_list_cache", None)
        st.session_state["notes_list_limit"] = limit

    if "notes_list_cache" not in st.session_state:
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
                return
            if response.ok:
                st.session_state["notes_list_cache"] = response.json()
            else:
                st.error(format_api_error(response, "Failed to load notes."))
                return

    notes = st.session_state.get("notes_list_cache", [])
    if not notes:
        st.info("No notes yet.")
        return

    for note in notes:
        title, body = _split_title_content(note.get("content", ""))
        with st.expander(title):
            if body:
                st.write(body)
            st.caption(
                f"ID: {note.get('id')} · Updated: {note.get('updated_at') or '-'}"
            )


def render_notes_page() -> None:
    st.header("Notes")
    token = st.session_state.get("access_token")
    if not token:
        st.info("Sign in to add notes.")
        return

    if "notes_view" not in st.session_state:
        st.session_state["notes_view"] = "Add note"
    if "notes_view_next" in st.session_state:
        st.session_state["notes_view"] = st.session_state.pop("notes_view_next")

    mode = st.sidebar.radio(
        "Notes menu",
        ["Add note", "List notes"],
        key="notes_view",
    )

    if mode == "Add note":
        with st.form("note-form"):
            title = st.text_input("Title")
            content = st.text_area("Content", height=200)
            submitted = st.form_submit_button("Save note")

        if submitted:
            if not title.strip():
                st.error("Title is required.")
                return
            if not content.strip():
                st.error("Content is required.")
                return
            note_text = f"{title.strip()}\n\n{content.strip()}"
            payload: dict[str, object] = {"content": note_text}

            try:
                response = api_request("POST", "/v1/notes", token=token, json=payload)
            except RuntimeError as exc:
                st.error(str(exc))
                return
            if response.ok:
                st.success(f"Queued note ingestion: {response.json().get('note_id')}")
                st.session_state.pop("notes_list_cache", None)
                st.session_state["notes_view_next"] = "List notes"
                st.rerun()
            else:
                st.error(format_api_error(response, "Failed to save note."))
    else:
        _render_notes_list(token)
