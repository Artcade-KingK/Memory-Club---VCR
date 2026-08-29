#!/usr/bin/env python3
"""
Boucle de lecture video automatique. Lit ~/playlist_config.json (gere depuis
la page web de transfert, section "Programmation de la lecture automatique")
pour savoir QUELLES playlists jouer, DANS QUEL ORDRE, et COMBIEN de videos
(aleatoires) prendre dans chacune a chaque tour de boucle.

Format de playlist_config.json : liste ordonnee de
    {"folder": "<nom du dossier sous ~/videos>", "count": <int>}
Un compteur a 0 = playlist ignoree (dossier de stockage uniquement, pas joue).
Ce fichier est cree et resynchronise automatiquement par upload_server.py ;
si ce script ne le trouve pas (ancienne installation), un reglage par defaut
equivalent au comportement historique (2 publicites + 1 film) est utilise.
"""
import json
import random
import subprocess
import time
from pathlib import Path

BASE_DIR = Path.home() / "videos"
CONFIG_FILE = Path.home() / "playlist_config.json"
EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}

# Utilise si playlist_config.json est absent ou illisible (ex: ancienne
# installation pas encore mise a jour) : reproduit le comportement d'origine.
DEFAULT_CONFIG = [
    {"folder": "publicite", "count": 2},
    {"folder": "film", "count": 1},
]


def load_config():
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            if isinstance(data, list):
                cleaned = [
                    {"folder": e["folder"], "count": int(e.get("count", 0))}
                    for e in data
                    if isinstance(e, dict) and "folder" in e
                ]
                if cleaned:
                    return cleaned
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return DEFAULT_CONFIG


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
        # Relu a chaque tour : un changement fait depuis la page web prend
        # effet des le tour de boucle suivant, sans redemarrer le Pi.
        config = load_config()
        active = [
            (entry["folder"], entry["count"])
            for entry in config
            if entry["count"] > 0
        ]

        if not active:
            print("Aucune playlist programmee (toutes a 0), attente 10s")
            time.sleep(10)
            continue

        any_played = False
        for folder_name, count in active:
            videos = get_videos(BASE_DIR / folder_name)
            if not videos:
                continue

            unique_count = min(count, len(videos))
            for video in random.sample(videos, unique_count):
                play(video)
                any_played = True

            # Si le nombre demande depasse ce qui est disponible, on complete
            # avec des tirages au hasard (avec repetition) plutot que de
            # jouer moins que ce qui a ete programme.
            for _ in range(count - unique_count):
                play(random.choice(videos))
                any_played = True

        if not any_played:
            print("Aucune video disponible dans les playlists programmees, attente 10s")
            time.sleep(10)


if __name__ == "__main__":
    main()
