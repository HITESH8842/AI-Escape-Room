"""
Version 2 - Reliable AI Escape Room (Streamlit UI)
Run:  streamlit run version2/app.py
"""

import base64
from pathlib import Path

import streamlit as st

from game import EscapeRoomGame
from game_engine import inventory_names, obj_name
from llm import GeminiLLM

# Style: V2 uses a cool moonlit blue theme (V1 uses warm candlelight gold),
# so the two versions are easy to tell apart.

# ---------------- Pictures ----------------
# The images/ folder sits next to version1/ and version2/.
IMAGE_DIR = Path(__file__).resolve().parent.parent / "images"


def find_image(name: str):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = IMAGE_DIR / f"{name}{ext}"
        if path.exists():
            return str(path)
    return None


def apply_theme(background, darkness: float = 0.55):
    """Blurred background, gold-framed banner, book-style chat and the Clue Journal."""
    css_bg = ""
    if background:
        path = Path(background)
        mime = "png" if path.suffix.lower() == ".png" else "webp" if path.suffix.lower() == ".webp" else "jpeg"
        data = base64.b64encode(path.read_bytes()).decode()
        css_bg = (f"background-image: linear-gradient(rgba(6,12,24,{darkness}), rgba(6,12,24,{darkness})), "
                  f"url('data:image/{mime};base64,{data}');")
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=Inter:wght@400;500;600&display=swap');
    .stApp {{ background-color:#0a1220; background-blend-mode: normal, luminosity; {css_bg}
             background-size: cover; background-position: center; background-attachment: fixed; }}
    [data-testid="stHeader"], [data-testid="stBottom"] > div {{ background: transparent; }}
    .block-container {{ padding-top: 2rem; max-width: 900px; }}
    [data-testid="stBottomBlockContainer"] {{ max-width: 900px; margin: 0 auto; }}
    [data-testid="stImage"] img {{ filter: saturate(.35) hue-rotate(190deg) brightness(.95) contrast(1.05); border-radius: 14px; border: 1px solid rgba(156,196,234,.55);
             box-shadow: 0 10px 40px rgba(0,0,0,.7); }}
    .subtitle {{ text-align:center; font-family:'Cinzel',serif; color:#9cc4ea; letter-spacing:.18em;
             font-size:.85rem; margin:.4rem 0 1.2rem; opacity:.9; }}
    [data-testid="stChatMessage"] {{ background: rgba(9,16,28,.78); border:1px solid rgba(156,196,234,.25);
             border-radius: 12px; padding: .9rem 1rem; backdrop-filter: blur(4px); }}
    [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {{ font-family:'Inter',system-ui,sans-serif;
             font-size:1.02rem; line-height:1.65; color:#e3edf7; }}
    [data-testid="stChatInput"] {{ border:1px solid rgba(156,196,234,.45) !important; border-radius:12px; }}
    [data-testid="stChatInput"], [data-testid="stChatInput"] * {{ border-color: rgba(156,196,234,.5) !important; }}
    [data-testid="stChatInput"] > div {{ background: rgba(9,16,28,.9) !important; }}
    .stButton button {{ border-color: rgba(156,196,234,.45) !important; background: rgba(9,16,28,.8); }}
    .stButton button:hover {{ color:#9cc4ea !important; border-color:#9cc4ea !important; }}
    [data-testid="stSidebar"] > div:first-child {{ background: rgba(8,14,24,.92); }}

    .journal {{ margin-top:.5rem; background: rgba(9,16,28,.85); border: 1px solid rgba(156,196,234,.45); border-radius: 14px;
             padding: 1.1rem 1.2rem; box-shadow: 0 10px 40px rgba(0,0,0,.6); }}
    .j-title {{ font-family:'Cinzel',serif; color:#9cc4ea; font-size:1.25rem; letter-spacing:.06em; }}
    .j-verified {{ display:inline-block; font-size:.7rem; letter-spacing:.08em; color:#08121f;
             background:#9cc4ea; border-radius:6px; padding:.1rem .45rem; margin:.25rem 0 .6rem; font-weight:600; }}
    .j-count {{ color:#9fb3c8; font-size:.85rem; margin-bottom:.4rem; }}
    .j-bar {{ height:6px; background:rgba(156,196,234,.18); border-radius:4px; overflow:hidden; margin-bottom:.3rem; }}
    .j-bar > div {{ height:100%; background:#9cc4ea; }}
    .j-head {{ font-family:'Cinzel',serif; color:#9cc4ea; font-size:.8rem; letter-spacing:.15em;
             text-transform:uppercase; margin:.9rem 0 .4rem; border-bottom:1px solid rgba(156,196,234,.25);
             padding-bottom:.25rem; }}
    .j-row {{ font-family:'Inter',system-ui,sans-serif; color:#e3edf7; font-size:.95rem; line-height:1.45;
             padding:.35rem 0; display:flex; gap:.5rem; align-items:flex-start; }}
    .j-row span:first-of-type {{ flex:1; }}
    .j-new {{ background:#9cc4ea; color:#08121f; font-size:.65rem; font-weight:700; border-radius:6px;
             padding:.1rem .4rem; margin-top:.25rem; height:fit-content; }}
    .j-empty {{ color:#6f8297; font-style:italic; font-family:'Inter',system-ui,sans-serif; }}
    .j-door {{ margin-top:.9rem; font-family:'Inter',system-ui,sans-serif; color:#e3edf7; font-size:1.05rem; }}
    </style>""", unsafe_allow_html=True)


# ---------------- Clue Journal (read from the ENGINE state, not from the LLM) ----------------
def clue_text(room: dict, clue) -> str:
    """Turn a clue id from the state into readable text using room.json."""
    if isinstance(clue, dict):
        return clue.get("text") or clue.get("description") or str(clue)
    clues = room.get("clues", {})
    entry = None
    if isinstance(clues, dict):
        entry = clues.get(clue)
    elif isinstance(clues, list):
        entry = next((c for c in clues if isinstance(c, dict) and c.get("id") == clue), None)
    if isinstance(entry, dict):
        return entry.get("text") or entry.get("description") or str(clue)
    if isinstance(entry, str):
        return entry
    return str(clue).replace("_", " ").capitalize()


def track_new(key: str, names: list, turn: int) -> list:
    """Remember in which turn each entry first appeared, so the newest can get a NEW badge."""
    seen = st.session_state.journal_seen.setdefault(key, {})
    for n in names:
        seen.setdefault(n, turn)
    return [(n, seen[n] == turn and turn > 0) for n in names]


def show_journal(room: dict, state: dict):
    turn = state["turns"]
    clues = track_new("clues", [clue_text(room, c) for c in state.get("discovered_clues", [])], turn)
    items = track_new("items", list(inventory_names(room, state)), turn)
    solved = len(state["solved_puzzles"])

    def rows(entries, icon):
        if not entries:
            return '<div class="j-empty">Nothing yet…</div>'
        return "".join(
            f'<div class="j-row">{icon} <span>{text}</span>{"<span class=j-new>NEW</span>" if new else ""}</div>'
            for text, new in entries)

    door = "🟢 Open" if state["door_open"] else "🔒 Locked"
    st.markdown(f"""
    <div class="journal">
      <div class="j-title">📘 Case File</div>
      <div class="j-verified">✔ Verified by the game engine</div>
      <div class="j-count">Puzzles solved: {solved} / 4</div>
      <div class="j-bar"><div style="width:{solved / 4 * 100:.0f}%"></div></div>
      <div class="j-head">Clues</div>{rows(clues, "◆")}
      <div class="j-head">Items in hand</div>{rows(items, "▸")}
      <div class="j-door">Door: {door}</div>
      <div class="j-door">Turns: {turn}</div>
    </div>""", unsafe_allow_html=True)


# The fixed opening text - shown at the start of every game.
STORY_INTRO = (
    "In 1897, head librarian **Eleanor Ashcombe** vanished without a trace. The town forgot her, "
    "and her library was locked for over a century. You're a student who fell asleep in the "
    "reading room and woke after closing time. The library has sealed itself. Before she "
    "disappeared, Eleanor turned it into a test: only a reader patient enough to follow her "
    "clues may leave.\n\nThe only way out is a heavy oak door with a **four-digit keypad**.\n\n"
    "*What do you do?*"
)


# ---------------- Game ----------------
st.set_page_config(page_title="The Forgotten Library v2", page_icon="🌙", layout="wide")
apply_theme(find_image("background"))


def start_new_game():
    st.session_state.game = EscapeRoomGame(llm=GeminiLLM())
    st.session_state.messages = [{"role": "assistant",
                                  "content": STORY_INTRO + " Type *help* if you are unsure what to do."}]
    st.session_state.journal_seen = {}   # the Clue Journal starts empty every game


if "game" not in st.session_state:
    start_new_game()

game: EscapeRoomGame = st.session_state.game
room, state = game.room, game.state

# ---------------- Sidebar: instructions + Case File ---------------- #
with st.sidebar:
    st.header("How to play")
    st.markdown(
        "You are locked in a library. Type what you want to do in plain English, e.g.\n"
        "- *look around*\n- *examine the bookshelf*\n- *take the key*\n"
        "- *use the key on the painting*\n- *enter 1234 on the door*\n- *inventory* / *hint*"
    )
    if st.button("🔄 Restart game", use_container_width=True):
        start_new_game()
        st.rerun()

    st.divider()
    show_journal(room, state)
    if game.llm is not None and game.llm.last_error:
        st.caption(f"⚠️ Last LLM error: {game.llm.last_error[:150]}")

# ---------------- Main: banner + chat ---------------- #
if find_image("banner"):
    st.image(find_image("banner"), width="stretch")
else:
    st.title("🗝️ The Forgotten Library")
    st.warning(f"Banner not found. Put banner.jpg or banner.png in: {IMAGE_DIR}")
st.markdown('<div class="subtitle">THE FORGOTTEN LIBRARIAN · VERSION 2</div>',
            unsafe_allow_html=True)

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if state["escaped"]:
    st.success(f"🎉 You escaped in {state['turns']} turns! Press Restart to play again.")

if prompt := st.chat_input("What do you do?", disabled=state["escaped"]):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("The Game Master is thinking..."):
        out = game.play_turn(prompt)
    st.session_state.messages.append({"role": "assistant", "content": out["text"]})
    if out["escaped"]:
        st.balloons()
    st.rerun()