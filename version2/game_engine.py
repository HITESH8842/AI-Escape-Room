"""
Game engine for Version 2.

This module is the "source of truth" for the game. Python (not the LLM) decides
whether an action succeeds. The LLM only receives the result and describes it.

Main ideas:
  * The room (objects, locks, codes, clues) is loaded from room.json.
  * The current game state is a plain Python dictionary (easy to show as JSON).
  * Every player action is turned into an Action and passed to execute().
  * execute() validates the action and returns a Result with factual text.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOM_FILE = Path(__file__).parent / "room.json"

VALID_VERBS = {
    "look", "examine", "take", "open", "use", "enter_code",
    "inventory", "hint", "help", "unknown",
}


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class Action:
    """A structured player action, produced by the parser."""
    verb: str                     # one of VALID_VERBS
    target: Optional[str] = None  # object id, e.g. "drawer"
    item: Optional[str] = None    # object id of the item being used, e.g. "brass_key"
    code: Optional[str] = None    # digits typed into a lock, e.g. "472"


@dataclass
class Result:
    """What happened. `message` is factual text the narrator must stick to."""
    success: bool
    message: str
    event: str = "none"           # short tag such as "opened", "invalid_object"
    new_clues: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Loading and state
# --------------------------------------------------------------------------- #
def load_room(path: Path = ROOM_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def new_state(room: dict) -> dict:
    """Create a fresh game state. Only *dynamic* information lives here."""
    return {
        "visible_objects": [oid for oid, o in room["objects"].items() if o.get("visible")],
        "inventory": [],
        "opened": [],             # objects whose lock has been opened
        "solved_puzzles": [],
        "discovered_clues": [],
        "examined": [],
        "door_open": False,
        "escaped": False,
        "wrong_attempts": 0,
        "turns": 0,
        "action_log": [],         # short history of validated actions
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def obj_name(room: dict, oid: str) -> str:
    return room["objects"][oid]["name"]


def is_available(state: dict, oid: str) -> bool:
    """An object can be interacted with if it is visible in the room or held."""
    return oid in state["visible_objects"] or oid in state["inventory"]


def _reveal(state: dict, oids: list) -> list:
    newly = []
    for oid in oids:
        if oid not in state["visible_objects"] and oid not in state["inventory"]:
            state["visible_objects"].append(oid)
            newly.append(oid)
    return newly


def _add_clue(state: dict, clue_id: Optional[str]) -> list:
    if clue_id and clue_id not in state["discovered_clues"]:
        state["discovered_clues"].append(clue_id)
        return [clue_id]
    return []


def _solve(state: dict, puzzle: Optional[str]) -> None:
    if puzzle and puzzle not in state["solved_puzzles"]:
        state["solved_puzzles"].append(puzzle)


def visible_names(room: dict, state: dict) -> list:
    return [obj_name(room, o) for o in state["visible_objects"]]


def inventory_names(room: dict, state: dict) -> list:
    return [obj_name(room, o) for o in state["inventory"]]


# --------------------------------------------------------------------------- #
# Action handlers  (each returns a Result and may change the state)
# --------------------------------------------------------------------------- #
def do_look(room, state, action) -> Result:
    names = ", ".join(visible_names(room, state))
    return Result(True, f"You look around the library. You can see: {names}.", "look")


def do_examine(room, state, action) -> Result:
    oid = action.target
    obj = room["objects"][oid]

    # Special case: the clock needs the magnifying glass to read the engraving.
    insp = obj.get("inspect_with")
    if insp and insp["item"] in state["inventory"] and insp["puzzle"] not in state["solved_puzzles"]:
        _solve(state, insp["puzzle"])
        clues = _add_clue(state, insp["clue"])
        return Result(True, insp["success_text"], "solved", clues)

    if oid in state["opened"] and obj.get("opened_description"):
        text = obj["opened_description"]
    elif insp and insp["puzzle"] in state["solved_puzzles"]:
        text = obj["description"].split(".")[0] + ". " + insp["success_text"]
    else:
        text = obj["description"]

    if oid not in state["examined"]:
        state["examined"].append(oid)

    newly = _reveal(state, obj.get("reveals_on_examine", []))
    clues = _add_clue(state, obj.get("clue_on_examine"))
    if newly:
        text += " You notice: " + ", ".join(obj_name(room, n) for n in newly) + "."
    return Result(True, text, "examined", clues)


def do_take(room, state, action) -> Result:
    oid = action.target
    obj = room["objects"][oid]
    if oid in state["inventory"]:
        return Result(False, f"You already have the {obj['name']}.", "already_have")
    if not obj.get("takeable"):
        return Result(False, f"The {obj['name']} cannot be taken.", "not_takeable")
    state["visible_objects"].remove(oid)
    state["inventory"].append(oid)
    return Result(True, f"You take the {obj['name']}.", "taken")


def do_enter_code(room, state, action) -> Result:
    oid = action.target
    obj = room["objects"][oid]
    lock = obj.get("lock")
    if not lock or lock["type"] != "code":
        return Result(False, f"The {obj['name']} has no keypad or combination lock.", "no_code_lock")
    if oid in state["opened"]:
        return Result(False, f"The {obj['name']} is already open.", "already_open")
    if not action.code or not action.code.isdigit() or len(action.code) != len(lock["code"]):
        return Result(False, f"The lock on the {obj['name']} needs exactly {len(lock['code'])} digits.", "bad_format")

    # Rule: the player must have found the clues (solved the earlier puzzles).
    missing = [p for p in lock.get("requires_puzzles", []) if p not in state["solved_puzzles"]]
    if missing or action.code != lock["code"]:
        state["wrong_attempts"] += 1
        return Result(False, f"You enter {action.code}. The lock on the {obj['name']} buzzes and stays shut. Wrong code.", "wrong_code")

    return _open_lock(room, state, oid, lock)


def do_open(room, state, action) -> Result:
    oid = action.target
    obj = room["objects"][oid]
    lock = obj.get("lock")
    if oid in state["opened"]:
        return Result(False, f"The {obj['name']} is already open.", "already_open")
    if not lock:
        return Result(False, f"The {obj['name']} is not something you can open.", "not_openable")
    if action.code:
        return do_enter_code(room, state, action)
    if lock["type"] == "code":
        return Result(False, f"The {obj['name']} is locked with a {len(lock['code'])}-digit code. You need to enter the code.", "locked")
    # item lock
    if action.item is None:
        need = lock["item"]
        if need in state["inventory"]:
            action.item = need  # player holds the right item: use it automatically
        else:
            return Result(False, f"The {obj['name']} is locked. There is a small keyhole.", "locked")
    return do_use(room, state, Action("use", target=oid, item=action.item))


def do_use(room, state, action) -> Result:
    item, oid = action.item, action.target
    if item is None:
        return Result(False, "Use what? Say for example 'use the key on the painting'.", "unclear")
    if item not in state["inventory"]:
        return Result(False, f"You don't have the {obj_name(room, item)}.", "not_in_inventory")
    if oid is None:
        return Result(False, f"Use the {obj_name(room, item)} on what?", "unclear")

    obj = room["objects"][oid]
    lock = obj.get("lock")
    if lock and lock["type"] == "item":
        if oid in state["opened"]:
            return Result(False, f"The {obj['name']} is already open.", "already_open")
        if lock["item"] != item:
            return Result(False, f"The {obj_name(room, item)} doesn't work on the {obj['name']}.", "wrong_item")
        return _open_lock(room, state, oid, lock)

    insp = obj.get("inspect_with")
    if insp and insp["item"] == item:
        return do_examine(room, state, Action("examine", target=oid))

    return Result(False, f"Nothing happens when you use the {obj_name(room, item)} on the {obj['name']}.", "no_effect")


def _open_lock(room, state, oid, lock) -> Result:
    state["opened"].append(oid)
    _solve(state, lock["puzzle"])
    _reveal(state, lock.get("reveals", []))
    clues = _add_clue(state, lock.get("clue"))
    if lock.get("escape"):
        state["door_open"] = True
        state["escaped"] = True
        return Result(True, lock["success_text"], "escaped", clues)
    return Result(True, lock["success_text"], "opened", clues)


def do_inventory(room, state, action) -> Result:
    items = inventory_names(room, state)
    return Result(True, "You are carrying: " + (", ".join(items) if items else "nothing") + ".", "inventory")


def do_hint(room, state, action) -> Result:
    for h in room["hints"]:
        if h["until_puzzle"] not in state["solved_puzzles"]:
            return Result(True, "Hint: " + h["text"], "hint")
    return Result(True, "You have everything you need.", "hint")


def do_help(room, state, action) -> Result:
    return Result(True, "Try things like: 'look around', 'examine the desk', 'take the key', "
                        "'use the key on the painting', 'enter 1234 on the door', 'inventory', 'hint'.", "help")


HANDLERS = {
    "look": do_look, "examine": do_examine, "take": do_take, "open": do_open,
    "use": do_use, "enter_code": do_enter_code, "inventory": do_inventory,
    "hint": do_hint, "help": do_help,
}

NEEDS_TARGET = {"examine", "take", "open", "enter_code"}


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def execute(room: dict, state: dict, action: Action) -> Result:
    """Validate and apply one action. Never raises for bad player input."""
    if state["escaped"]:
        return Result(False, "You have already escaped. Press 'Restart' to play again.", "game_over")

    state["turns"] += 1

    if action.verb not in VALID_VERBS or action.verb == "unknown":
        return Result(False, "That action isn't possible here. Type 'help' to see what you can do.", "unknown")

    # Validate referenced objects: they must exist AND be available to the player.
    for ref in (action.target, action.item):
        if ref is not None and ref not in room["objects"]:
            return Result(False, "There is no such thing in this room.", "invalid_object")
    if action.target is not None and not is_available(state, action.target):
        return Result(False, "You don't see anything like that here.", "not_visible")
    if action.item is not None and action.item not in state["inventory"]:
        if is_available(state, action.item):
            return Result(False, f"You need to pick up the {obj_name(room, action.item)} first.", "not_in_inventory")
        return Result(False, "You don't have anything like that.", "not_in_inventory")

    if action.verb in NEEDS_TARGET and action.target is None:
        names = ", ".join(visible_names(room, state))
        return Result(False, f"You don't see anything like that here. Things you can interact with: {names}.", "unclear")

    before = copy.deepcopy(state)
    try:
        result = HANDLERS[action.verb](room, state, action)
    except Exception as exc:  # safety net: never leave a half-changed state
        state.clear()
        state.update(before)
        return Result(False, f"Something went wrong ({exc}). Nothing changed.", "error")

    state["action_log"].append({
        "turn": state["turns"], "verb": action.verb, "target": action.target,
        "item": action.item, "success": result.success, "event": result.event,
    })
    return result


def known_facts(room: dict, state: dict) -> list:
    """Clue texts the player has actually discovered (safe to give to the LLM)."""
    return [room["clues"][c] for c in state["discovered_clues"]]


def secret_codes(room: dict) -> dict:
    """All lock codes, used by the output guard to detect leaks."""
    return {oid: o["lock"]["code"] for oid, o in room["objects"].items()
            if o.get("lock", {}).get("type") == "code"}
