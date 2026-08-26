# memory-vcr

Kiosque vidéo Raspberry Pi : démarre automatiquement et joue en boucle infinie une
séquence de vidéos (2 publicités aléatoires + 1 film aléatoire, en continu), en sortie
HDMI vers un convertisseur HDMI→AV relié à une station RF analogique (télé cathodique).

## Matériel visé

- Raspberry Pi 4B
- Raspberry Pi OS Lite (64-bit), Bookworm
- Convertisseur HDMI→AV branché sur le port **HDMI0** du Pi (le plus proche de l'USB-C)
- Sortie forcée en 4:3 (640x480) pour correspondre à une télé cathodique via RF/composite

Si ton matériel diffère (autre port HDMI, écran natif 16:9, etc.), regarde `config/xorg-10-hdmi-4-3.conf`
et `scripts/videoloop.py` (device audio ALSA `hdmi:CARD=vc4hdmi0,DEV=0`) — ce sont les deux
endroits à adapter.

## Installation

1. Flashe une carte SD avec **Raspberry Pi OS Lite (64-bit) Bookworm** via
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Dans les options avancées
   (roue crantée), configure : nom d'hôte, utilisateur/mot de passe, Wi-Fi si besoin, et
   **active SSH**.
2. Démarre le Pi, connecte-toi en SSH :
   ```bash
   ssh <utilisateur>@<ip-du-pi>
   ```
3. Lance l'installation en une commande :
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Artcade-KingK/Memory-Club---VCR/main/install.sh | bash
   ```
   Le script va : installer les paquets nécessaires (X11, Openbox, VLC, Flask), déployer les
   scripts, configurer le démarrage automatique (autologin console → X11 → boucle vidéo),
   forcer la sortie HDMI en 4:3, installer et démarrer le service web de transfert des vidéos,
   puis redémarrer le Pi.
4. Pendant l'installation, il te sera demandé de choisir un mot de passe pour l'interface web
   de transfert des vidéos (ou laisse vide pour en générer un automatiquement — il sera affiché
   à la fin, note-le).

Relancer la même commande plus tard met à jour le code et conserve le mot de passe déjà choisi.

> **Écran noir avec juste le curseur de la souris après le redémarrage ?** C'est normal sur une
> carte SD toute neuve : les dossiers `publicite` et `film` sont vides, donc `videoloop.py`
> (déjà lancé en arrière-plan par Openbox) attend simplement de trouver des vidéos — il retente
> toutes les 10 secondes sans jamais planter, d'où l'écran noir sans wallpaper ni rien d'affiché.
> Ajoute des vidéos via l'interface web (`http://<ip-du-pi>:8080/`, voir section **Utilisation**
> ci-dessous : au moins 2 dans `Publicite` et 1 dans `Film`) et la lecture démarre automatiquement
> dans les 10 secondes qui suivent, sans avoir besoin de redémarrer quoi que ce soit.

## Utilisation

- **Ajouter des vidéos** : ouvre `http://<ip-du-pi>:8080/` dans un navigateur sur le même
  réseau, identifiant `memory-club`, mot de passe choisi à l'installation. Upload par
  sélection de fichiers, choix du dossier (Publicité / Film), suppression possible.
- Formats acceptés : `.mp4`, `.avi`, `.mkv`, `.mov`.
- La boucle vidéo prend automatiquement en compte les nouvelles vidéos (pas besoin de
  redémarrer le Pi).

## Script BoxCutter

Un script PowerShell qui retire automatiquement les bandes noires **verticales** (pillarbox,
gauche/droite) d'un dossier de vidéos sources, avant leur transfert vers le Pi.

Il utilise le filtre `cropdetect` de `ffmpeg`/`ffprobe` pour analyser chaque vidéo et détecter
précisément où commence et où finit l'image réelle, puis réencode une copie recadrée dans un
sous-dossier `Boxed`. Les fichiers originaux ne sont jamais modifiés.

**Important** : seule la largeur est recadrée, la hauteur n'est jamais touchée — même si
`ffmpeg` détecte des bandes horizontales (letterbox, haut/bas). Une bande verticale signifie
qu'une image 4:3 flotte dans un cadre 16:9 (à corriger), tandis qu'une bande horizontale
signifie généralement qu'un film large (16:9/cinémascope) est incrusté dans un cadre 4:3 —
très courant sur les bandes-annonces des années 90. La retirer rendrait la vidéo plus large
que 4:3, et VLC recréerait alors lui-même du pillarbox à la lecture pour compenser, puisque
le Pi force une sortie fixe en 4:3.

Tu le pointes vers un dossier (ex. `.\BoxCutter.ps1 -Path "C:\Users\XXX\Downloads\videos\"`) et il
traite automatiquement tous les fichiers à l'intérieur, pour que toutes tes vidéos remplissent
correctement un cadre 4:3 avant d'arriver sur la télé cathodique.

**Installer ffmpeg :**
```powershell
winget install --id Gyan.FFmpeg -e
```

Télécharge le script `BoxCutter.ps1` (`tools/BoxCutter.ps1` dans ce dépôt).

**PowerShell :**
```powershell
powershell -ExecutionPolicy Bypass -File "C:\XXX\BoxCutter.ps1" -Path "C:\Users\XXX\Downloads\videos"
```

Un recadrage de moins de 5% de la largeur est ignoré par défaut (pas assez significatif pour
justifier un réencodage complet). Ce seuil est ajustable avec `-MinCropPercent` :

```powershell
powershell -ExecutionPolicy Bypass -File "C:\XXX\BoxCutter.ps1" -Path "C:\Users\XXX\Downloads\videos" -MinCropPercent 10
```

## Structure du dépôt

```
install.sh                     script d'installation unique (one-liner)
scripts/videoloop.py           boucle de lecture vidéo (VLC en ligne de commande)
scripts/upload_server.py       interface web de transfert des vidéos (Flask)
config/xinitrc                 lance Openbox au démarrage de X11
config/openbox-autostart       désactive l'économiseur d'écran, lance videoloop.py
config/xorg-10-hdmi-4-3.conf   force la sortie HDMI en 640x480 (4:3), ignore l'EDID
systemd/vcr-upload.service     service systemd pour l'interface web (port 8080)
tools/BoxCutter.ps1            (PC Windows) retire les bandes noires des videos avant transfert
```

## Notes techniques (pièges rencontrés pendant le développement)

- **Son en sortie HDMI** : sur Pi 4, chaque sortie HDMI est une carte ALSA séparée
  (`vc4hdmi0`/`vc4hdmi1`). Le device `default` ne pointe pas forcément dessus, et l'accès
  direct (`hw:`/`plughw:`) n'accepte que le format IEC958 (pas du PCM classique). Solution :
  cibler explicitement `hdmi:CARD=vc4hdmi0,DEV=0` (visible via `aplay -L`), déjà fait dans
  `videoloop.py`.
- **Bandes noires malgré des vidéos déjà en 4:3** : le Pi sort par défaut en HDMI 16:9
  (720p), et VLC plein écran rajoute lui-même du pillarbox pour respecter l'aspect ratio de
  la vidéo. Sur Bookworm (pilote KMS complet), les réglages `hdmi_group`/`hdmi_mode`/`hdmi_cvt`
  de `config.txt` et le paramètre noyau `video=` de `cmdline.txt` sont **insuffisants** — le
  pilote `modesetting` d'Xorg fait sa propre détection EDID indépendante. Solution : un
  `xorg.conf.d` qui ignore complètement l'EDID (`IgnoreEDID`/`NoDDC`) et impose un mode fixe
  (`config/xorg-10-hdmi-4-3.conf`), installé automatiquement par `install.sh`.
- **Stockage vidéos** : sur la carte SD directement (pas de clé USB — le montage automatique
  via udev s'est avéré peu fiable sur ce setup).

## Diagnostic

```bash
sudo systemctl status vcr-upload.service     # etat du service web
sudo ss -tlnp | grep 8080                    # verifier qu'un seul process ecoute sur le port
DISPLAY=:0 xrandr                            # resolution/etat vus par X11
aplay -l ; aplay -L                          # cartes son et devices logiques disponibles
```

## Liens utiles

- [ytdlp.online](https://ytdlp.online/) — téléchargement en lot (batch) de vidéos YouTube,
  pratique pour récupérer des publicités/films à ajouter dans `publicite`/`film`.
- [Playlist de 400+ bandes-annonces de films des années 90](https://youtube.com/playlist?list=PLxARvl8pPDO-T7QuuQlNUMCadqyXr_OBW&si=TH20KhbHGWm8NqXF) —
  bonne source de contenu pour le dossier `film`.
