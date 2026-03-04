"""Course generation page.

User pastes text or uploads a PDF.
The app structures the course and generates flashcards + quiz from that content.
The number of modules and lessons is determined automatically by the model.

Location: quiz_app/pages/0_Generate.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import io
import streamlit as st
from database import init_db
from auth_guard import require_auth, render_sidebar_user, current_user_id

init_db()

st.set_page_config(page_title="Learnly — Create a course", layout="wide")

require_auth()
render_sidebar_user()

st.title("Create a course")

# ---------------------------------------------------------------------------
# Résolution de la clé Groq : st.secrets en priorité, sinon os.environ
# ---------------------------------------------------------------------------
def _get_groq_api_key() -> str | None:
    try:
        key = st.secrets.get("GROQ_API_KEY") or st.secrets.get("groq_api_key")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")

def _get_groq_model() -> str:
    try:
        model = st.secrets.get("GROQ_MODEL") or st.secrets.get("groq_model")
        if model:
            return model
    except Exception:
        pass
    return os.environ.get("GROQ_MODEL", "llama3-70b-8192")

GROQ_API_KEY = _get_groq_api_key()
GROQ_MODEL = _get_groq_model()

if not GROQ_API_KEY:
    st.error(
        "**GROQ_API_KEY manquante.**\n\n"
        "**En local :** ajoutez la clé dans le fichier `.env` :\n"
        "```\nGROQ_API_KEY=your_key_here\n```\n\n"
        "**Sur Streamlit Cloud :** ajoutez la clé dans "
        "**Settings → Secrets** de votre application :\n"
        "```toml\nGROQ_API_KEY = \"your_key_here\"\n```\n\n"
        "Clé gratuite disponible sur [console.groq.com](https://console.groq.com)."
    )
    st.stop()

# Injecter dans os.environ pour que agent.py et config.py les trouvent
os.environ["GROQ_API_KEY"] = GROQ_API_KEY
os.environ["GROQ_MODEL"] = GROQ_MODEL

CHUNK_THRESHOLD = 4000

level_map = {"Beginner": "beginner", "Intermediate": "intermediate", "Advanced": "advanced"}


def extract_pdf_text(uploaded_file) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(uploaded_file.read()))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    except ImportError:
        st.error("pypdf is not installed. Run: pip install pypdf")
        return ""


def _display_generation(agent_fn) -> None:
    st.divider()

    status_placeholder = st.empty()
    progress_placeholder = st.empty()

    current_module: dict = {"label": "", "index": 0, "total": 0}

    def on_text(text: str) -> None:
        if "module(s)" in text and "—" in text:
            try:
                total = int(text.split("module(s)")[0].split()[-1])
                current_module["total"] = total
            except (ValueError, IndexError):
                pass

    def on_tool_call(name: str, args: dict) -> None:
        action = args.get("action", "")

        if action == "create_course":
            title = args.get("title", "")
            status_placeholder.info(f"⏳ Setting up course **{title}**...")

        elif action == "add_module":
            current_module["label"] = args.get("title", "")
            current_module["index"] += 1
            idx = current_module["index"]
            total = current_module["total"]
            label = current_module["label"]
            if total:
                status_placeholder.info(f"⏳ Module {idx}/{total}: **{label}**")
            else:
                status_placeholder.info(f"⏳ Module: **{label}**")
            progress_placeholder.empty()

        elif action == "add_lesson":
            lesson = args.get("title") or args.get("objective", "")
            progress_placeholder.caption(f"Generating lesson: *{lesson}*")

    def on_tool_result(name: str, result: str) -> None:
        pass

    status_placeholder.info("⏳ Generation in progress... (30–90 seconds depending on course size)")

    try:
        final_message = agent_fn(on_text, on_tool_call, on_tool_result)
        progress_placeholder.empty()
        status_placeholder.success("✅ Course created successfully!")
        if final_message:
            st.info(final_message)
        st.balloons()
        st.page_link("app.py", label="← Back to home to view your course")
    except Exception as exc:
        progress_placeholder.empty()
        status_placeholder.error(f"Generation failed: {exc}")


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------

with st.form("generate_form"):
    course_title = st.text_input(
        "Course title",
        placeholder="e.g. Introduction to Machine Learning",
    )

    level_c = st.selectbox("Level", list(level_map.keys()))

    input_method = st.radio(
        "Content source",
        ["Paste text", "Upload PDF"],
        horizontal=True,
    )

    pasted_text = st.text_area(
        "Paste your content here",
        height=250,
        placeholder="Paste the text you want to turn into a course...",
    )

    uploaded_pdf = st.file_uploader("Upload a PDF", type=["pdf"])

    extra_c = st.text_area(
        "Additional instructions (optional)",
        height=80,
        placeholder="e.g. Focus on practical examples, include code snippets...",
    )

    publish_notion_c = st.checkbox(
        "Publish to Notion after generation",
        value=bool(st.session_state.get("notion_token")),
    )

    submitted = st.form_submit_button("Generate course", type="primary", use_container_width=True)

if submitted:
    if not course_title.strip():
        st.warning("Please enter a course title.")
        st.stop()

    uid = current_user_id()
    if not uid:
        st.error("Session expired. Please log in again.")
        st.stop()

    raw_content = ""
    if input_method == "Paste text":
        if not pasted_text.strip():
            st.warning("Please paste some content.")
            st.stop()
        raw_content = pasted_text.strip()
    else:
        if uploaded_pdf is None:
            st.warning("Please upload a PDF file.")
            st.stop()
        with st.spinner("Extracting PDF text..."):
            raw_content = extract_pdf_text(uploaded_pdf)
        if not raw_content:
            st.error("Could not extract text from this PDF.")
            st.stop()

    if len(raw_content) > CHUNK_THRESHOLD:
        nb_chars = len(raw_content)
        auto_modules = max(2, min(5, nb_chars // 3000))
        st.info(
            f"Content detected: **{nb_chars:,} characters**. "
            f"Generation in **{auto_modules + 1} steps** to respect API limits "
            f"(~1 minute wait between each step)."
        )

    from agent import run_agent_chunked

    def _run(on_text, on_tool_call, on_tool_result):
        return run_agent_chunked(
            content=raw_content,
            course_title=course_title.strip(),
            level=level_map[level_c],
            num_modules=max(2, min(5, len(raw_content) // 3000)),
            num_lessons=2,
            extra_instructions=extra_c.strip(),
            on_text=on_text,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            publish_to_notion=publish_notion_c,
            user_id=uid,
        )

    _display_generation(_run)