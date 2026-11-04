"""Optional CLI equivalent of the first-run download screen."""
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doc_anon.resources import prepare

last = 0


def progress(message, done, total):
    global last
    if time.monotonic() - last > 3:
        print(f'{message}: {done / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB', flush=True)
        last = time.monotonic()


if __name__ == '__main__':
    prepare(progress)
    print('Risorse verificate. Pronto offline.', flush=True)
