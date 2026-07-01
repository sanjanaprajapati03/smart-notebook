import time

import markdown as _md
import requests
import streamlit as st

from ui.api import api_request, format_api_error

_LANGUAGETOOL_URL = "https://api.languagetool.org/v2/check"
_DEBOUNCE_SECONDS = 1.0


def _split_title_content(text: str) -> tuple[str, str]:
    if not text:
        return "Untitled", ""
    lines = text.splitlines()
    title = lines[0].strip() if lines else ""
    if not title:
        title = "Untitled"
    body = "\n".join(lines[1:]).lstrip()
    return title, body


def _check_grammar(text: str) -> list[dict]:
    if not text.strip():
        return []
    try:
        resp = requests.post(
            _LANGUAGETOOL_URL,
            data={"text": text, "language": "en-US"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("matches", [])
    except Exception:
        return []


def _render_grammar_feedback(matches: list[dict]) -> None:
    if not matches:
        return
    count = len(matches)
    st.warning(f"Found {count} potential issue{'s' if count > 1 else ''}")
    for match in matches[:5]:
        ctx = match.get("context", {})
        snippet = ctx.get("text", "")
        offset = ctx.get("offset", 0)
        length = ctx.get("length", 0)
        word = snippet[offset : offset + length]
        msg = match.get("message", "")
        repls = [r.get("value", "") for r in match.get("replacements", [])[:3]]
        line = f"**{word}** — {msg}"
        if repls:
            line += f"  \nSuggestions: {', '.join(repls)}"
        st.caption(line)
    if count > 5:
        st.caption(f"... and {count - 5} more issues")


def _grammar_check_section(text: str, label: str, field_key: str) -> bool:
    if not text.strip():
        return False

    cache_key = f"_grammar_{field_key}"
    time_key = f"_grammar_ts_{field_key}"
    text_key = f"_grammar_txt_{field_key}"

    now = time.time()
    last_time = st.session_state.get(time_key, 0.0)
    last_text = st.session_state.get(text_key, "")

    if text == last_text and cache_key in st.session_state:
        matches = st.session_state[cache_key]
    elif text == last_text and now - last_time < _DEBOUNCE_SECONDS:
        matches = st.session_state.get(cache_key, [])
    else:
        matches = _check_grammar(text)
        st.session_state[cache_key] = matches
        st.session_state[time_key] = now
        st.session_state[text_key] = text

    if matches:
        st.markdown(f"**{label}:**")
        _render_grammar_feedback(matches)
        return True
    return False


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
                st.markdown(body)
            st.caption(
                f"ID: {note.get('id')} · Updated: {note.get('updated_at') or '-'}"
            )


def _check_duplicate_title(token: str, title: str) -> str | None:
    try:
        resp = api_request("GET", "/v1/notes", token=token, params={"limit": 200})
        if not resp.ok:
            return None
        for note in resp.json():
            existing_title, _ = _split_title_content(note.get("content", ""))
            if existing_title.lower() == title.strip().lower():
                return existing_title
    except Exception:
        return None
    return None


def _render_add_note_form(token: str) -> None:
    if st.session_state.pop("_clear_form", False):
        for k in ["note_title", "note_content", "_content_trigger"]:
            st.session_state.pop(k, None)

    if "note_title" not in st.session_state:
        st.session_state["note_title"] = ""
    if "note_content" not in st.session_state:
        st.session_state["note_content"] = ""

    st.text_input("_t", key="_content_trigger", label_visibility="collapsed")
    st.markdown(
        """
        <script>
        (function() {
            try {
                var ta = document.querySelector('textarea');
                var tg = document.querySelector('input[aria-label="_t"]');
                if (!ta || !tg) return;
                if (ta._sn_h) ta.removeEventListener('input', ta._sn_h);
                if (window._sn_cls === undefined) window._sn_cls = '';
                ta._sn_h = function() {
                    if (this.value === window._sn_cls) return;
                    window._sn_cls = this.value;
                    var s = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    );
                    s.set.call(tg, Date.now().toString());
                    tg.dispatchEvent(new Event('input', {bubbles: true}));
                };
                ta.addEventListener('input', ta._sn_h);
            } catch(e) {}
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

    editor_col, preview_col = st.columns([1, 1])

    with editor_col:
        st.subheader("Editor")
        title = st.text_input("Title", key="note_title")
        content = st.text_area("Content", height=300, key="note_content")

        if st.button("Save note"):
            if not title.strip():
                st.error("Title is required.")
            elif not content.strip():
                st.error("Content is required.")
            else:
                dup = _check_duplicate_title(token, title)
                if dup:
                    st.error(f"A note titled **{dup}** already exists. Choose a different title.")
                    st.stop()
                note_text = f"{title.strip()}\n\n{content.strip()}"
                try:
                    response = api_request(
                        "POST", "/v1/notes", token=token, json={"content": note_text}
                    )
                except RuntimeError as exc:
                    st.error(str(exc))
                    return
                if response.ok:
                    st.success(
                        f"Queued note ingestion: {response.json().get('note_id')}"
                    )
                    st.session_state.pop("notes_list_cache", None)
                    st.session_state["_clear_form"] = True
                    st.session_state["notes_view_next"] = "List notes"
                    st.rerun()
                else:
                    st.error(format_api_error(response, "Failed to save note."))

    with preview_col:
        st.subheader("Preview")
        preview_placeholder = st.empty()
        if title.strip() or content.strip():
            combined_md = f"# {title}\n\n{content}" if title.strip() else content
            combined_html = _md.markdown(combined_md)
            preview_placeholder.markdown(
                f'<div style="max-height:400px;overflow-y:auto;padding:8px;'
                f'border:1px solid #ddd;border-radius:4px;">'
                f'{combined_html}</div>',
                unsafe_allow_html=True,
            )
        else:
            preview_placeholder.info("Start typing to see a preview...")

    if title.strip() or content.strip():
        st.divider()
        st.subheader("Grammar & Spelling")
        found_any = False
        if title.strip():
            found_any |= _grammar_check_section(title, "Title", "title")
        if content.strip():
            found_any |= _grammar_check_section(content, "Content", "content")
        if not found_any:
            st.success("No issues found!")


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
        _render_add_note_form(token)
    else:
        _render_notes_list(token)
