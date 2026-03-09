import streamlit as st
import pandas as pd

from shared.db import get_engine

st.set_page_config(page_title="RAG Sync Monitor", layout="wide")

engine = get_engine()

page = st.sidebar.selectbox("Page", [
    "Users", "Files", "Sync History", "File Status", "Department", "Errors",
])

if page == "Users":
    st.header("Users")
    df = pd.read_sql("""
        SELECT u.user_id, u.usr_name, u.email, d.name AS department,
               r.role_name, u.is_active, u.last_login, u.created_at
        FROM users u
        JOIN department d ON u.dept_id = d.dept_id
        JOIN roles r ON u.role_id = r.role_id
        ORDER BY u.created_at DESC
    """, engine)
    departments = ["All"] + df["department"].unique().tolist() if not df.empty else ["All"]
    dept_filter = st.selectbox("Department", departments)
    if dept_filter != "All":
        df = df[df["department"] == dept_filter]
    st.dataframe(df, use_container_width=True)

elif page == "Files":
    st.header("Documents")
    df = pd.read_sql("""
        SELECT doc.doc_id, doc.file_name, doc.type, doc.status,
               d.name AS department, doc.created_at
        FROM document doc
        JOIN department d ON doc.dept_id = d.dept_id
        ORDER BY doc.created_at DESC
    """, engine)
    status_filter = st.selectbox(
        "Status", ["All", "pending", "processing", "indexed", "failed"],
    )
    if status_filter != "All":
        df = df[df["status"] == status_filter]
    st.dataframe(df, use_container_width=True)

elif page == "Sync History":
    st.header("Sync History")
    df = pd.read_sql(
        "SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 100", engine,
    )
    st.dataframe(df, use_container_width=True)
    if not df.empty:
        chart_data = df[
            ["started_at", "files_added", "files_modified", "files_deleted"]
        ].set_index("started_at")
        st.bar_chart(chart_data)

elif page == "File Status":
    st.header("File Status Distribution")
    df = pd.read_sql(
        "SELECT status, COUNT(*) AS count FROM document GROUP BY status", engine,
    )
    if not df.empty:
        st.bar_chart(df.set_index("status"))

elif page == "Department":
    st.header("Indexed Files per Department")
    df = pd.read_sql("""
        SELECT d.name AS department, COUNT(*) AS count
        FROM document doc
        JOIN department d ON doc.dept_id = d.dept_id
        WHERE doc.status = 'indexed'
        GROUP BY d.name
    """, engine)
    if not df.empty:
        st.bar_chart(df.set_index("department"))

elif page == "Errors":
    st.header("Pipeline Errors")
    df = pd.read_sql("""
        SELECT pl.id, doc.file_name, pl.stage, pl.status,
               pl.error_message, pl.started_at
        FROM pipeline_logs pl
        JOIN document doc ON pl.doc_id = doc.doc_id
        WHERE pl.status = 'failed'
        ORDER BY pl.started_at DESC
        LIMIT 100
    """, engine)
    st.dataframe(df, use_container_width=True)
