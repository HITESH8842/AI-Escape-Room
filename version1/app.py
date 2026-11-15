"""
Version 1 - Interactive AI Escape Room (Streamlit UI)
The LLM is the Game Master AND the rule keeper. Run:  streamlit run version1/app.py
"""

import base64
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPT, INTRO, ESCAPE_TOKEN

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# The fixed opening text - shown at the start of every game (same story as Version 2).
STORY_INTRO = (
    "In 1897, head librarian **Eleanor Ashcombe** vanished without a trace. The town forgot her, "
    "and her library was locked for over a century. You're a student who fell asleep in the "
    "reading room and woke after closing time. The library has sealed itself. Before she "
    "disappeared, Eleanor turned it into a test: only a reader patient enough to follow her "
    "clues may leave.\n\nThe only way out is a heavy oak door with a **four-digit keypad**.\n\n"
    "*What do you do?*"
)

# ---------------- Pictures ----------------
# The images/ folder sits next to version1/ and version2/.
IMAGE_DIR = Path(__file__).resolve().parent.parent / "images"

# V1 has no game state, so the scene picture is chosen from keywords in the player's
# message (most specific keywords first). It cannot know if e.g. the drawer is open.
SCENE_KEYWORDS = [
    ("red book", "red_books"), ("bookshelf", "bookshelf"), ("shelf", "bookshelf"),
    ("book", "bookshelf"), ("drawer", "drawer"), ("painting", "painting"),
    ("portrait", "painting"), ("clock", "clock"), ("keypad", "door"),
    ("door", "door"), ("exit", "door"), ("journal", "desk"), ("magnif", "desk"),
    ("desk", "desk"), ("look around", "start"),
]


def find_image(name: str):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = IMAGE_DIR / f"{name}{ext}"
        if path.exists():
            return str(path)
    return None


def image_for(player_message: str):
    text = player_message.lower()
    for keyword, scene in SCENE_KEYWORDS:
        if keyword in text:
            return find_image(scene)
    return None


def apply_theme(background, darkness: float = 0.55):
    """Blurred background, gold-framed banner and book-style chat bubbles."""
    css_bg = ""
    if background:
        path = Path(background)
        mime = "png" if path.suffix.lower() == ".png" else "webp" if path.suffix.lower() == ".webp" else "jpeg"
        data = base64.b64encode(path.read_bytes()).decode()
        css_bg = (f"background-image: linear-gradient(rgba(10,6,3,{darkness}), rgba(10,6,3,{darkness})), "
                  f"url('data:image/{mime};base64,{data}');")
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=EB+Garamond:wght@400;500&display=swap');
    .stApp {{ background-color:#120b06; {css_bg}
             background-size: cover; background-position: center; background-attachment: fixed; }}
    [data-testid="stHeader"], [data-testid="stBottom"] > div {{ background: transparent; }}
    .block-container {{ padding-top: 2rem; max-width: 820px; }}
    [data-testid="stImage"] img {{ border-radius: 14px; border: 1px solid rgba(212,162,76,.55);
             box-shadow: 0 10px 40px rgba(0,0,0,.7); }}
    .subtitle {{ text-align:center; font-family:'Cinzel',serif; color:#d4a24c; letter-spacing:.18em;
             font-size:.85rem; margin:.4rem 0 1.2rem; opacity:.9; }}
    [data-testid="stChatMessage"] {{ background: rgba(20,13,8,.78); border:1px solid rgba(212,162,76,.25);
             border-radius: 12px; padding: .9rem 1rem; backdrop-filter: blur(4px); }}
    [data-testid="stChatMessage"] p {{ font-family:'EB Garamond',Georgia,serif; font-size:1.15rem;
             line-height:1.6; color:#f1e6d2; }}
    [data-testid="stChatInput"] {{ border:1px solid rgba(212,162,76,.45) !important; border-radius:12px; }}
    [data-testid="stSidebar"] > div:first-child {{ background: rgba(18,11,6,.92); }}
    </style>""", unsafe_allow_html=True)


# ---------------- Page header ----------------
st.set_page_config(page_title="The Forgotten Library", page_icon="📚")
apply_theme(find_image("background"))

if find_image("banner"):
    st.image(find_image("banner"), width="stretch")
else:
    st.title("📚 The Forgotten Library")
    st.warning(f"Banner not found. Put banner.jpg or banner.png in: {IMAGE_DIR}")
st.markdown('<div class="subtitle">VERSION 1 · THE LLM IS THE GAME MASTER</div>',
            unsafe_allow_html=True)

if not API_KEY:
    st.error("GEMINI_API_KEY is missing. Copy .env.example to .env and add your key.")
    st.stop()


def send_with_retry(message: str, tries: int = 3) -> str:
    """Send a message to Gemini. Retry if the server is busy (503) or rate-limited (429)."""
    for attempt in range(tries):
        try:
            return st.session_state.chat.send_message(message).text or ""
        except Exception as exc:
            temporary = "503" in str(exc) or "429" in str(exc)
            if temporary and attempt < tries - 1:
                time.sleep(3 * (attempt + 1))   # wait 3s, then 6s
                continue
            raise   # give up: the caller shows the error


def new_game():
    # Keep the client in session_state: if it is only a local variable, Python
    # garbage-collects it and closes the connection ("client has been closed").
    st.session_state.client = genai.Client(api_key=API_KEY)
    # A chat session keeps the full conversation history -> this is the game "memory".
    st.session_state.chat = st.session_state.client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.8),
    )
    st.session_state.messages = [{"role": "assistant", "content": STORY_INTRO, "image": find_image("start")}]
    st.session_state.escaped = False


if "chat" not in st.session_state:
    new_game()

with st.sidebar:
    st.header("How to play")
    st.markdown(
        "Find the clues, solve the puzzles and open the door.\n\n"
        "Just type what you want to do, e.g. *examine the bookshelf* or "
        "*try 123 on the drawer*."
    )
    if st.button("🔄 Restart game", use_container_width=True):
        new_game()
        st.rerun()

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("image"):
            st.image(m["image"], width="stretch")
        st.markdown(m["content"])

if st.session_state.escaped:
    st.success("🎉 You escaped! Press Restart to play again.")

if prompt := st.chat_input("What do you do?", disabled=st.session_state.escaped):
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        with st.spinner("The Game Master is thinking..."):
            reply = send_with_retry(prompt)
    except Exception as exc:
        reply = f"⚠️ The Game Master could not answer: {exc}"

    image = image_for(prompt)

    # V1 trusts the LLM completely: if it writes the token, the player has escaped.
    if ESCAPE_TOKEN in reply:
        image = find_image("escaped")
        st.session_state.escaped = True
        reply = reply.replace(ESCAPE_TOKEN, "").strip()
        st.balloons()

    st.session_state.messages.append({"role": "assistant", "content": reply, "image": image})
    st.rerun()