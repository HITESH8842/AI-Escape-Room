"""
Glue code: one player turn = parse -> validate/execute -> narrate.
Used by both the Streamlit app and the command-line version.
"""

from __future__ import annotations

from game_engine import load_room, new_state, execute
from parser import parse
from narrator import narrate


class EscapeRoomGame:
    def __init__(self, llm=None, room=None):
        self.llm = llm
        self.room = room or load_room()
        self.state = new_state(self.room)

    def restart(self):
        self.state = new_state(self.room)

    def intro(self) -> str:
        return self.room["intro"] + " Type 'help' if you are unsure what to do."

    def play_turn(self, message: str) -> dict:
        action = parse(message, self.room, self.llm)
        result = execute(self.room, self.state, action)
        text, guarded = narrate(self.llm, self.room, self.state, message, result)
        return {
            "text": text,
            "action": action.__dict__,
            "success": result.success,
            "event": result.event,
            "guard_triggered": guarded,
            "escaped": self.state["escaped"],
        }
