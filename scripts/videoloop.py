#!/usr/bin/env python3
import random
import subprocess
import time
from pathlib import Path

PUB_DIR = Path.home() / "videos" / "publicite"
FILM_DIR = Path.home() / "videos" / "film"
EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}


def get_videos(folder):
    if not folder.exists():
        return []
    return [f for f in folder.iterdir() if f.suffix.lower() in EXTENSIONS]


def play(video):
    subprocess.run([
        "cvlc", "--play-and-exit", "--fullscreen",
        "--no-osd", "--no-video-title-show",
        "--aout=alsa",
        "--alsa-audio-device=hdmi:CARD=vc4hdmi0,DEV=0",
        str(video)
    ])


def main():
    while True:
        pubs = get_videos(PUB_DIR)
        films = get_videos(FILM_DIR)

        if len(pubs) < 2 or not films:
            print("Pas assez de videos dans un des dossiers, attente 10s")
            time.sleep(10)
            continue

        for video in random.sample(pubs, 2):
            play(video)

        play(random.choice(films))


if __name__ == "__main__":
    main()
