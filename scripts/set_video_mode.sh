#!/usr/bin/env bash
# ============================================================
# vcr-set-video-mode - bascule la sortie video du Pi entre HDMI et
# composite (jack 3.5mm -> RCA).
#
# Les deux modes ne peuvent PAS coexister sur un Pi 4 : la sortie composite
# native (VEC) partage une horloge avec le circuit HDMI, l'activer coupe
# entierement HDMI au niveau materiel (voir CLAUDE.md / README pour le
# detail de cette decouverte). Ce script applique donc TOUJOURS un seul mode
# a la fois : il retire completement la configuration de l'autre avant
# d'appliquer le mode demande.
#
# Doit tourner en root :
#   - appele directement par install.sh (deja root via sudo apt/cp, etc.)
#   - appele par upload_server.py (utilisateur normal) via une regle sudo
#     dediee, restreinte a "vcr-set-video-mode hdmi" et
#     "vcr-set-video-mode composite" (voir /etc/sudoers.d/vcr-video-mode)
#
# Usage : vcr-set-video-mode <hdmi|composite> [--no-reboot]
#   --no-reboot : applique la config mais ne redemarre pas (utilise par
#                 install.sh, qui gere lui-meme son propre redemarrage final)
# ============================================================
set -euo pipefail

MODE="${1:-}"
FLAG="${2:-}"

if [ "$MODE" != "hdmi" ] && [ "$MODE" != "composite" ]; then
    echo "Usage: $0 <hdmi|composite> [--no-reboot]" >&2
    exit 1
fi

if [ "$(id -u)" != "0" ]; then
    echo "Ce script doit etre execute en root (via sudo)." >&2
    exit 1
fi

CONFIG_TXT="/boot/firmware/config.txt"
STATE_DIR="/etc/memory-vcr"
STATE_FILE="$STATE_DIR/video-mode"
XORG_DIR="/etc/X11/xorg.conf.d"
HDMI_CONF_SRC="$STATE_DIR/xorg-hdmi.conf"
COMPOSITE_CONF_SRC="$STATE_DIR/xorg-composite.conf"
HDMI_CONF_DST="$XORG_DIR/10-hdmi-4-3.conf"
COMPOSITE_CONF_DST="$XORG_DIR/10-composite-4-3.conf"

mkdir -p "$STATE_DIR" "$XORG_DIR"

# Sauvegarde ponctuelle de config.txt avant la toute premiere modification,
# pour pouvoir revenir en arriere a la main en cas de probleme imprevu.
if [ ! -f "${CONFIG_TXT}.orig" ]; then
    cp "$CONFIG_TXT" "${CONFIG_TXT}.orig"
fi

if [ "$MODE" = "composite" ]; then
    echo "Activation du mode composite dans $CONFIG_TXT..."
    sed -i -E 's/^dtoverlay=vc4-kms-v3d(,composite=1)?$/dtoverlay=vc4-kms-v3d,composite=1/' "$CONFIG_TXT"
    grep -qxF 'enable_tvout=1' "$CONFIG_TXT" || echo 'enable_tvout=1' >> "$CONFIG_TXT"
    grep -qxF 'sdtv_mode=2'   "$CONFIG_TXT" || echo 'sdtv_mode=2'   >> "$CONFIG_TXT"
    grep -qxF 'sdtv_aspect=1' "$CONFIG_TXT" || echo 'sdtv_aspect=1' >> "$CONFIG_TXT"

    rm -f "$HDMI_CONF_DST"
    if [ -f "$COMPOSITE_CONF_SRC" ]; then
        cp "$COMPOSITE_CONF_SRC" "$COMPOSITE_CONF_DST"
    else
        echo "Attention : $COMPOSITE_CONF_SRC introuvable, xorg.conf.d non mis a jour pour le composite." >&2
    fi
else
    echo "Activation du mode HDMI dans $CONFIG_TXT..."
    sed -i -E 's/^dtoverlay=vc4-kms-v3d,composite=1$/dtoverlay=vc4-kms-v3d/' "$CONFIG_TXT"
    sed -i '/^enable_tvout=1$/d' "$CONFIG_TXT"
    sed -i '/^sdtv_mode=2$/d'   "$CONFIG_TXT"
    sed -i '/^sdtv_aspect=1$/d' "$CONFIG_TXT"

    rm -f "$COMPOSITE_CONF_DST"
    if [ -f "$HDMI_CONF_SRC" ]; then
        cp "$HDMI_CONF_SRC" "$HDMI_CONF_DST"
    else
        echo "Attention : $HDMI_CONF_SRC introuvable, xorg.conf.d non mis a jour pour le HDMI." >&2
    fi
fi

echo "$MODE" > "$STATE_FILE"
chmod 644 "$STATE_FILE"

echo "Mode video regle sur : $MODE"

if [ "$FLAG" = "--no-reboot" ]; then
    echo "(--no-reboot demande, pas de redemarrage)"
    exit 0
fi

# Le redemarrage est differe de quelques secondes et detache du script, pour
# laisser au process appelant (ex: la requete HTTP dans upload_server.py) le
# temps de repondre avant que le systeme ne s'eteigne.
echo "Redemarrage dans 3 secondes pour appliquer le nouveau mode video..."
(sleep 3 && reboot) &
disown
exit 0
