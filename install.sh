#!/usr/bin/env bash
# ============================================================
# memory-vcr - installation automatique
#
# Usage (depuis une carte SD Raspberry Pi OS Lite 64-bit Bookworm
# fraichement flashee, connecte en SSH) :
#
#   curl -fsSL https://raw.githubusercontent.com/Artcade-KingK/Memory-Club---VCR/main/install.sh | bash
#
# Reexecutable sans risque : relancer la meme commande met a jour
# le code et conserve le mot de passe web deja choisi.
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/Artcade-KingK/Memory-Club---VCR.git"
BRANCH="main"
SRC_DIR="$HOME/.memory-vcr-src"

VIDEOS_PUB="$HOME/videos/publicite"
VIDEOS_FILM="$HOME/videos/film"

log()  { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" = "0" ]; then
    die "Ne lance pas ce script en root (pas de 'sudo' devant la commande). Lance-le en tant qu'utilisateur normal : il demandera sudo lui-meme quand necessaire."
fi

command -v sudo >/dev/null 2>&1 || die "sudo est requis mais introuvable."

log "Installation de memory-vcr pour l'utilisateur $(whoami) (home: $HOME)"

# --- 1. Paquets systeme ---------------------------------------------------
log "Installation des paquets systeme (peut prendre quelques minutes)..."
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    git \
    xserver-xorg x11-xserver-utils xinit openbox \
    vlc \
    python3-flask

# --- 2. Recuperation du code -----------------------------------------------
log "Recuperation du code source..."
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC_DIR" reset --hard "origin/$BRANCH"
else
    rm -rf "$SRC_DIR"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$SRC_DIR"
fi

# --- 3. Dossiers videos -----------------------------------------------------
log "Creation des dossiers videos..."
mkdir -p "$VIDEOS_PUB" "$VIDEOS_FILM"

# --- 4. Mot de passe interface web -----------------------------------------
DEPLOYED_UPLOAD="$HOME/upload_server.py"
EXISTING_PASSWORD=""
if [ -f "$DEPLOYED_UPLOAD" ]; then
    EXISTING_PASSWORD=$(grep -oP '(?<=^PASSWORD = ")[^"]*' "$DEPLOYED_UPLOAD" 2>/dev/null | head -n1 || true)
    if [ "$EXISTING_PASSWORD" = "CHANGE_ME" ]; then
        EXISTING_PASSWORD=""
    fi
fi

UPLOAD_PASSWORD=""
if [ -n "$EXISTING_PASSWORD" ]; then
    log "Mot de passe existant de l'interface web conserve (installation deja faite auparavant)."
    UPLOAD_PASSWORD="$EXISTING_PASSWORD"
else
    if [ -r /dev/tty ]; then
        echo ""
        echo "Choisis un mot de passe pour l'interface web de transfert des videos"
        echo "(laisse vide et appuie sur Entree pour en generer un automatiquement) :"
        read -r -s -p "Mot de passe : " UPLOAD_PASSWORD < /dev/tty || true
        echo ""
    fi
    if [ -z "$UPLOAD_PASSWORD" ]; then
        UPLOAD_PASSWORD=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
        log "Mot de passe genere automatiquement (note-le, affiche une seule fois) : $UPLOAD_PASSWORD"
    fi
fi

# --- 5. Deploiement des scripts ---------------------------------------------
log "Deploiement des scripts..."
cp "$SRC_DIR/scripts/videoloop.py" "$HOME/videoloop.py"
cp "$SRC_DIR/scripts/upload_server.py" "$HOME/upload_server.py"
sed -i "s/PASSWORD = \"CHANGE_ME\"/PASSWORD = \"$UPLOAD_PASSWORD\"/" "$HOME/upload_server.py"
chmod +x "$HOME/videoloop.py" "$HOME/upload_server.py"

# --- 6. Environnement graphique (X11 + Openbox) -----------------------------
log "Configuration de l'environnement graphique..."
mkdir -p "$HOME/.config/openbox"
cp "$SRC_DIR/config/xinitrc" "$HOME/.xinitrc"
cp "$SRC_DIR/config/openbox-autostart" "$HOME/.config/openbox/autostart"
chmod +x "$HOME/.xinitrc" "$HOME/.config/openbox/autostart"

BASHRC_LINE='if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then startx; fi'
if ! grep -qF "$BASHRC_LINE" "$HOME/.bashrc" 2>/dev/null; then
    printf '\n%s\n' "$BASHRC_LINE" >> "$HOME/.bashrc"
fi

# --- 7. Sortie HDMI forcee en 4:3 -------------------------------------------
log "Configuration de la sortie HDMI en 4:3 (ignore l'EDID du convertisseur HDMI->AV)..."
sudo mkdir -p /etc/X11/xorg.conf.d
sudo cp "$SRC_DIR/config/xorg-10-hdmi-4-3.conf" /etc/X11/xorg.conf.d/10-hdmi-4-3.conf

# --- 8. Service web de transfert des videos ---------------------------------
log "Installation du service web de transfert des videos (port 8080)..."
sudo cp "$SRC_DIR/systemd/vcr-upload.service" /etc/systemd/system/vcr-upload.service
sudo sed -i "s|__HOME__|$HOME|g; s|__USER__|$(whoami)|g" /etc/systemd/system/vcr-upload.service
sudo systemctl daemon-reload
sudo systemctl enable --now vcr-upload.service

# --- 9. Autologin console ----------------------------------------------------
log "Configuration de l'autologin console..."
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_boot_behaviour B2 \
        || warn "Impossible de configurer l'autologin automatiquement (raspi-config nonint do_boot_behaviour B2 a echoue). A faire manuellement via : sudo raspi-config -> System Options -> Boot / Auto Login -> Console Autologin."
else
    warn "raspi-config introuvable, autologin console a configurer manuellement."
fi

# --- 10. Recapitulatif -------------------------------------------------------
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
IP="${IP:-<ip-du-pi>}"

log "Installation terminee !"
echo ""
echo "  Videos a deposer dans :"
echo "    $VIDEOS_PUB"
echo "    $VIDEOS_FILM"
echo ""
echo "  Interface web de transfert : http://$IP:8080/"
echo "    Utilisateur  : memory-club"
echo "    Mot de passe : $UPLOAD_PASSWORD"
echo ""
echo "  Branche le convertisseur HDMI->AV sur le port HDMI0 du Pi"
echo "  (le port le plus proche de l'alimentation USB-C)."
echo ""
echo "  Le Pi va redemarrer dans 10 secondes pour appliquer tous les reglages."
echo "  Ctrl+C maintenant pour annuler le redemarrage."
sleep 10
sudo reboot
