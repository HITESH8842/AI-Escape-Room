"""Play Version 2 in the terminal:  python version2/play_cli.py"""

from game import EscapeRoomGame
from llm import GeminiLLM


def main():
    llm = GeminiLLM()
    game = EscapeRoomGame(llm=llm)
    print("LLM narrator:", "ON (" + llm.model + ")" if llm.available else "OFF (offline mode)")
    print(game.intro())
    while not game.state["escaped"]:
        try:
            msg = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ("quit", "exit game"):
            break
        if msg.lower() == "restart":
            game.restart()
            print(game.intro())
            continue
        out = game.play_turn(msg)
        print(out["text"])
    if game.state["escaped"]:
        print(f"\n*** You escaped in {game.state['turns']} turns! ***")


if __name__ == "__main__":
    main()
