"""Hand-written agent harness. One file per responsibility; every runtime
action is printed with the name of the file that performed it."""
import os


def logger(file: str):
    name = os.path.basename(file)

    def log(msg: str) -> None:
        print(f"[{name}] {msg}", flush=True)

    return log
