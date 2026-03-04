"""Quiz App — Home / Quiz Setup Page.

Run with:
    streamlit run quiz_app/app.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from database import init_db, get_db
from models import Course, QuizAttempt
from sqlalchemy import select
from auth_guard import require_auth, render_sidebar_user, current_user_id
from tools.quiz_tool import manage_quiz

init_db()

st.set_page_config(page_title="Learnly", page_icon="📚", layout="wide")

require_auth()
render_sidebar_user()

st.title("Learnly")
st.caption("Select lessons, then start a quiz or study flashcards.")

# Show Notion connection status if a token is stored in the session
if st.session_state.get("notion_token"):
    token_val = st.session_state["notion_token"]
    masked = token_val[:10] + "..." + token_val[-4:]
    st.info(
        f"Notion connected ({masked}). "
        "You can publish courses automatically after generation. "
        "To change accounts, go to the Notion Connection page."
    )

# Load all courses for the current user
with get_db() as db:
    stmt = select(Course).order_by(Course.title)
    uid = current_user_id()
    if uid:
        stmt = stmt.where(Course.user_id == uid)
    courses = db.scalars(stmt).all()

    course_data = []
    for course in courses:
        modules_data = []
        for module in course.modules:
            lessons_data = []
            for lesson in module.lessons:
                has_quizzes = len(lesson.quiz_attempts) > 0
                has_flashcards = len(lesson.flashcards) > 0
                quiz_types = set()
                for attempt in lesson.quiz_attempts:
                    for q in (attempt.questions or []):
                        quiz_types.add(q.get("type", "single"))
                lessons_data.append({
                    "id": lesson.id,
                    "title": lesson.title,
                    "is_completed": lesson.is_completed,
                    "has_quizzes": has_quizzes,
                    "has_flashcards": has_flashcards,
                    "quiz_types": quiz_types,
                    "latest_attempt_id": (
                        lesson.quiz_attempts[0].id if lesson.quiz_attempts else None
                    ),
                })
            if lessons_data:
                modules_data.append({
                    "id": module.id,
                    "title": module.title,
                    "lessons": lessons_data,
                })
        if modules_data:
            course_data.append({
                "id": course.id,
                "title": course.title,
                "topic": course.topic,
                "modules": modules_data,
                "notion_page_id": course.notion_page_id,
            })

if not course_data:
    st.info("No courses found. Create one from the Generate page.")
    st.stop()

# Step 1: select courses
st.subheader("Step 1: Select courses")
all_course_titles = {c["title"]: c for c in course_data}
selected_course_titles = st.multiselect(
    "Which courses do you want to study?",
    options=list(all_course_titles.keys()),
    default=list(all_course_titles.keys()),
)

if not selected_course_titles:
    st.info("Select at least one course to continue.")
    st.stop()

selected_courses = [all_course_titles[t] for t in selected_course_titles]

# Step 2: select lessons
st.subheader("Step 2: Select lessons")
selected_lesson_ids: list[int] = []

for course in selected_courses:
    st.markdown(f"**{course['title']}**")
    for module in course["modules"]:
        st.caption(module["title"])
        for lesson in module["lessons"]:
            badges = []
            if lesson["has_quizzes"]:
                badges.append("Quiz")
            if lesson["has_flashcards"]:
                badges.append("Flashcards")
            if lesson["is_completed"]:
                badges.append("Completed")
            label = lesson["title"]
            if badges:
                label += f" [{', '.join(badges)}]"

            if not lesson["has_quizzes"]:
                st.caption(f"{lesson['title']} — no quiz available")
                continue

            checked = st.checkbox(label, value=True, key=f"lesson_{lesson['id']}")
            if checked:
                selected_lesson_ids.append(lesson["id"])

if not selected_lesson_ids:
    st.info("Select at least one lesson with a quiz to continue.")
    st.stop()

# Step 3: quiz settings
st.subheader("Step 3: Quiz settings")
num_questions = st.slider("Questions per lesson", min_value=1, max_value=20, value=5)

all_quiz_types = set()
for course in selected_courses:
    for module in course["modules"]:
        for lesson in module["lessons"]:
            if lesson["id"] in selected_lesson_ids:
                all_quiz_types.update(lesson["quiz_types"])

type_options = ["All"]
if "single" in all_quiz_types:
    type_options.append("Single answer")
if "multi" in all_quiz_types:
    type_options.append("Multi-select")

question_type_filter = st.selectbox("Question type", options=type_options)

type_map = {"All": None, "Single answer": "single", "Multi-select": "multi"}
selected_type = type_map.get(question_type_filter)

# Notion publish option
st.subheader("Step 4: Publish to Notion (optional)")

session_token = st.session_state.get("notion_token")
session_root = st.session_state.get("notion_root_page_id")

courses_with_notion = [c for c in selected_courses if c.get("notion_page_id")]
courses_without_notion = [c for c in selected_courses if not c.get("notion_page_id")]

if session_token:
    publish_options = [c["title"] for c in selected_courses]
    courses_to_publish_titles = st.multiselect(
        "Courses to publish to Notion",
        options=publish_options,
        default=[c["title"] for c in courses_without_notion],
    )
    courses_to_publish = {
        title: all_course_titles[title]
        for title in courses_to_publish_titles
    }

    if courses_with_notion:
        st.caption(
            "Note: republishing will replace existing Notion pages."
        )

    if st.button("Publish to Notion", use_container_width=False):
        from tools import manage_notion_page

        for title, course in courses_to_publish.items():
            try:
                result = manage_notion_page(
                    action="publish_course",
                    course_id=course["id"],
                    api_key=session_token,
                    root_page_id=session_root,
                )
                action_label = "Republished" if course.get("notion_page_id") else "Published"
                st.success(
                    f"{title} — {action_label}, {result['pages_created']} pages created"
                )
            except Exception as e:
                st.error(f"{title} — {e}")
else:
    st.divider()
    st.info(
        "Connect your Notion account to publish courses. "
        "Go to the Notion Connection page in the menu."
    )

# Start quiz
st.divider()
if st.button("Start Quiz", type="primary", use_container_width=True):
    all_attempts = []

    with get_db() as db:
        for course in selected_courses:
            for module in course["modules"]:
                for lesson in module["lessons"]:
                    if lesson["id"] not in selected_lesson_ids:
                        continue

                    all_stored_questions = []
                    seen_questions: set[str] = set()

                    stmt = (
                        select(QuizAttempt)
                        .where(QuizAttempt.lesson_id == lesson["id"])
                        .order_by(QuizAttempt.created_at.desc())
                    )
                    stored_attempts = db.scalars(stmt).all()

                    for stored in stored_attempts:
                        for q in (stored.questions or []):
                            qtext = q.get("question", "")
                            if qtext in seen_questions:
                                continue
                            if selected_type and q.get("type", "single") != selected_type:
                                continue
                            seen_questions.add(qtext)
                            all_stored_questions.append(q)

                    if not all_stored_questions:
                        continue

                    questions_subset = all_stored_questions[:num_questions]

                    new_attempt = QuizAttempt(
                        lesson_id=lesson["id"],
                        questions=questions_subset,
                        max_score=float(10 * len(questions_subset)),
                    )
                    db.add(new_attempt)
                    db.flush()

                    all_attempts.append({
                        "attempt_id": new_attempt.id,
                        "lesson_id": lesson["id"],
                        "lesson_title": lesson["title"],
                        "module_title": module["title"],
                        "course_title": course["title"],
                        "num_questions": len(questions_subset),
                    })

    if not all_attempts:
        st.warning("No quiz questions found for the selected lessons and filters.")
    else:
        st.session_state["quiz_attempts"] = all_attempts
        st.session_state["quiz_answers"] = {}
        st.switch_page("pages/1_Take_Quiz.py")