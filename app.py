import os
import tempfile
import bcrypt
import streamlit as st
from pymongo import MongoClient
from embedchain import App
from docx import Document

# MongoDB Connection
def get_mongo_client():
    mongo_uri = st.secrets["MONGO_URI"]
    return MongoClient(mongo_uri)

def get_user_by_email(email):
    client = get_mongo_client()
    db = client["test"]
    users_collection = db["users"]
    return users_collection.find_one({"email": email})

def validate_user(email, password):
    user = get_user_by_email(email)
    if user and bcrypt.checkpw(password.encode('utf-8'), user["Password"].encode('utf-8')):
        return user
    return None

# Embedchain Setup
def read_docx(file_path):
    try:
        document = Document(file_path)
        return "\n".join([para.text for para in document.paragraphs])
    except Exception as e:
        raise Exception(f"Error reading DOCX file: {e}")

def process_and_add_file(file, file_type, app):
    try:
        temp_file_name = None
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=f".{file_type}") as f:
            f.write(file.getvalue())
            temp_file_name = f.name

        if temp_file_name:
            if file_type == "pdf":
                st.markdown(f"Adding PDF {file.name} to knowledge base...")
                app.add(temp_file_name, data_type="pdf_file")
            elif file_type == "docx":
                st.markdown(f"Adding DOCX {file.name} to knowledge base...")
                content = read_docx(temp_file_name)
                app.add(content, data_type="text")  # Adding as text
            st.markdown(f"Successfully added {file.name}!")
            st.session_state.messages.append({"role": "assistant", "content": f"Added {file.name} to knowledge base!"})
        return file.name
    except Exception as e:
        st.error(f"Error adding {file.name} to knowledge base: {e}")
        return None
    finally:
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)

def embedchain_bot(db_path, api_key):
    return App.from_config(
        config={
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.5,
                    "max_tokens": 1000,
                    "top_p": 1,
                    "stream": True,
                    "api_key": api_key,
                },
            },
            "vectordb": {
                "provider": "chroma",
                "config": {"collection_name": "chat-doc", "dir": db_path, "allow_reset": True},
            },
            "embedder": {"provider": "openai", "config": {"api_key": api_key}},
            "chunker": {"chunk_size": 2000, "chunk_overlap": 0, "length_function": "len"},
        }
    )

def get_db_path():
    tmpdirname = tempfile.mkdtemp()
    st.info(tmpdirname)
    return tmpdirname

def get_ec_app(api_key):
    if "app" in st.session_state:
        app = st.session_state.app
    else:
        db_path = get_db_path()
        app = embedchain_bot(db_path, api_key)
        st.session_state.app = app
    return app

# Streamlit App
st.set_page_config(page_title="DocGPT", page_icon="📄", layout="wide")

with st.sidebar:
    if "user" not in st.session_state:
        # Login Interface
        st.title("Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = validate_user(email, password)
            if user:
                st.success(f"Welcome, {user['Firstname']}!")
                st.session_state.user = user
                st.session_state.add_doc_files = []  # Initialize user-specific file storage
                st.rerun()
            else:
                st.error("Invalid email or password.")
    else:
        # Dynamic Sidebar for Logged-in Users
        st.success(f"Logged in as {st.session_state.user['Firstname']}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

        # File Upload Section
        st.markdown("### Upload Your Documents")
        app = get_ec_app(st.secrets["OPEN_AI_KEY"])
        doc_files = st.file_uploader(
            "Upload your documents (PDF, DOCX)", 
            accept_multiple_files=True, 
            type=["pdf", "docx"]
        )

        if "add_doc_files" not in st.session_state:
            st.session_state["add_doc_files"] = []

        for doc_file in doc_files:
            file_name = doc_file.name
            file_extension = file_name.split(".")[-1].lower()

            if file_name in st.session_state["add_doc_files"]:
                continue

            processed_file_name = process_and_add_file(doc_file, file_extension, app)
            if processed_file_name:
                st.session_state["add_doc_files"].append(file_name)

# Main Chat Interface
if "user" in st.session_state:
    st.title(f"Welcome, {st.session_state.user['Firstname']}! 📄")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Hi! I'm DocGPT. Upload your documents (PDF, DOCX), and I’ll answer your questions about them!"
            }
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask me anything!"):
        app = get_ec_app(st.secrets["OPEN_AI_KEY"])

        with st.chat_message("user"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.markdown(prompt)

        with st.chat_message("assistant"):
            msg_placeholder = st.empty()
            msg_placeholder.markdown("Thinking...")
            full_response = ""

            for response in app.chat(prompt):
                msg_placeholder.empty()
                full_response += response

            st.write(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
else:
    st.warning("Please log in to access the application.")
