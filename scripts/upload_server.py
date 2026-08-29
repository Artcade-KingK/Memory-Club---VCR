#!/usr/bin/env python3
"""
Petit serveur web pour transferer facilement les videos publicite/film
sur le Raspberry Pi, sans passer par scp/PowerShell.

Accessible depuis n'importe quel navigateur du reseau local a :
    http://<ip-du-pi>:8080/

Identifiants : voir USERNAME / PASSWORD ci-dessous.
Ce fichier est deploye par install.sh, qui remplace automatiquement la
valeur par defaut du mot de passe par un mot de passe reel genere ou
choisi a l'installation. Si tu modifies ce fichier a la main, pense a
changer le mot de passe avant usage reel.
"""

import json
import shutil
from functools import wraps
from pathlib import Path

from flask import (
    Flask, request, redirect, url_for, flash, Response, render_template_string, jsonify
)
from werkzeug.utils import secure_filename

# --- A CONFIGURER ---------------------------------------------------------
USERNAME = "memory-club"
PASSWORD = "CHANGE_ME"          # <-- remplace par install.sh, ou change-le ici
PORT = 8080
# ---------------------------------------------------------------------------

BASE_DIR = Path.home() / "videos"
EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}

# Dossiers par defaut, toujours presents et impossibles a supprimer depuis la
# page web (utilises par videoloop.py pour la boucle de lecture automatique).
DEFAULT_FOLDERS = ["publicite", "film"]
PROTECTED_FOLDERS = set(DEFAULT_FOLDERS)
FOLDER_LABELS = {"publicite": "Publicite", "film": "Film"}

# Fichier de programmation de la boucle automatique, lu independamment par
# videoloop.py. Format : liste ordonnee de {"folder": nom, "count": n} — n
# videos (aleatoires) sont jouees depuis ce dossier a chaque tour, dans
# l'ordre de la liste. n=0 -> dossier non joue automatiquement (stockage
# seulement). L'ordre de cette liste = ordre de lecture.
PLAYLIST_CONFIG_FILE = Path.home() / "playlist_config.json"
DEFAULT_PLAYLIST_CONFIG = [
    {"folder": "publicite", "count": 2},
    {"folder": "film", "count": 1},
]
MAX_PLAYLIST_COUNT = 50

app = Flask(__name__)
app.secret_key = "memory-vcr-upload-secret"  # session locale uniquement, pas besoin d'etre secret

PAGE = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transfert videos - memory-vcr</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; background:#111; color:#eee; }
  h1 { font-size: 1.4rem; }
  .section-header { display:flex; justify-content:space-between; align-items:center; margin-top:2rem; border-bottom:1px solid #333; padding-bottom:.3rem; }
  .section-header h2 { margin:0; }
  h2 { font-size: 1.1rem; }
  button.clear-all { background:#a33; color:white; border:none; padding:.3rem .8rem; border-radius:5px; cursor:pointer; font-size:.85rem; }
  button.clear-all:hover { background:#c44; }
  .section-actions { display:flex; gap:.5rem; }
  form.newfolder { display:flex; gap:.6rem; align-items:center; }
  form.newfolder input[type=text] { flex:1; padding:.5rem; border-radius:6px; border:1px solid #333; background:#111; color:#eee; }
  .msg { background:#234; padding:.6rem 1rem; border-radius:6px; margin-bottom:1rem; }
  form.upload { background:#1a1a1a; padding:1rem; border-radius:8px; margin-bottom:1.5rem; }
  fieldset { border:none; margin:0 0 .8rem 0; padding:0; }
  label { margin-right:1rem; }
  input[type=submit] { background:#2a6; color:white; border:none; padding:.5rem 1.2rem; border-radius:6px; cursor:pointer; }
  input[type=submit]:hover { background:#3b7; }
  ul { list-style:none; padding:0; }
  li { display:flex; justify-content:space-between; align-items:center; padding:.4rem 0; border-bottom:1px solid #222; }
  .size { color:#888; font-size:.85rem; margin-left:.5rem; }
  button.del { background:#a33; color:white; border:none; padding:.3rem .7rem; border-radius:5px; cursor:pointer; }
  button.del:hover { background:#c44; }
  .empty { color:#777; font-style:italic; }
  .storage { margin:.8rem 0 1.4rem 0; }
  .storage-label { display:flex; justify-content:space-between; font-size:.85rem; color:#ccc; margin-bottom:.3rem; }
  .storage-bar { background:#333; border-radius:6px; height:10px; overflow:hidden; }
  .storage-fill { background:#2a6; height:100%; transition:width .3s ease; }
  .playlist-config { background:#1a1a1a; padding:1rem; border-radius:8px; margin-bottom:1.5rem; }
  .playlist-config h2 { margin-top:0; }
  .playlist-config .hint { color:#999; font-size:.85rem; margin:-.3rem 0 .9rem 0; }
  .config-list { list-style:none; padding:0; margin:0; }
  .config-list li { display:flex; align-items:center; gap:.7rem; padding:.5rem 0; border-bottom:1px solid #222; }
  .config-list li:last-child { border-bottom:none; }
  .config-order { display:flex; flex-direction:column; gap:.15rem; }
  .config-order form { margin:0; }
  .config-order button, .config-count button { background:#333; color:#eee; border:none; width:1.8rem; height:1.6rem; border-radius:4px; cursor:pointer; font-size:.8rem; line-height:1; }
  .config-order button:hover:not(:disabled), .config-count button:hover:not(:disabled) { background:#444; }
  .config-order button:disabled, .config-count button:disabled { opacity:.3; cursor:default; }
  .config-name { flex:1; }
  .config-count { display:flex; align-items:center; gap:.5rem; margin-left:auto; }
  .config-count form { margin:0; }
  .count-value { min-width:1.6rem; text-align:center; font-variant-numeric:tabular-nums; }
  #progress-wrap { display:none; margin:.8rem 0; }
  #progress-bar { background:#333; border-radius:6px; height:18px; overflow:hidden; }
  #progress-fill { background:#2a6; height:100%; width:0%; transition:width .15s ease; }
  #progress-text { margin-top:.3rem; font-size:.85rem; color:#ccc; }
</style>
</head>
<body>
<h1>Transfert videos - memory-vcr</h1>

<div class="storage">
  <div class="storage-label">
    <span>Espace disque</span>
    <span>{{ disk.used_gb }} Go / {{ disk.total_gb }} Go utilises ({{ disk.free_gb }} Go restants)</span>
  </div>
  <div class="storage-bar">
    <div class="storage-fill" style="width: {{ disk.pct_used }}%;{% if disk.pct_used >= 90 %} background:#a33;{% elif disk.pct_used >= 75 %} background:#c93;{% endif %}"></div>
  </div>
</div>

{% with messages = get_flashed_messages() %}
  {% if messages %}
    {% for m in messages %}<div class="msg">{{ m }}</div>{% endfor %}
  {% endif %}
{% endwith %}

<div class="playlist-config">
  <h2>Programmation de la lecture automatique</h2>
  <p class="hint">
    Ordre de passage et nombre de videos jouees par playlist a chaque tour de boucle.
    Une valeur a 0 = playlist non jouee automatiquement (stockage seulement).
  </p>
  <ul class="config-list">
  {% for entry in playlist_config %}
    <li>
      <div class="config-order">
        <form method="post" action="{{ url_for('move_playlist') }}">
          <input type="hidden" name="folder" value="{{ entry.folder }}">
          <input type="hidden" name="direction" value="up">
          <button type="submit" {% if loop.first %}disabled{% endif %}>&#9650;</button>
        </form>
        <form method="post" action="{{ url_for('move_playlist') }}">
          <input type="hidden" name="folder" value="{{ entry.folder }}">
          <input type="hidden" name="direction" value="down">
          <button type="submit" {% if loop.last %}disabled{% endif %}>&#9660;</button>
        </form>
      </div>
      <span class="config-name">{{ labels.get(entry.folder, entry.folder) }}</span>
      <div class="config-count">
        <form method="post" action="{{ url_for('count_playlist') }}">
          <input type="hidden" name="folder" value="{{ entry.folder }}">
          <input type="hidden" name="action" value="dec">
          <button type="submit" {% if entry.count == 0 %}disabled{% endif %}>-</button>
        </form>
        <span class="count-value">{{ entry.count }}</span>
        <form method="post" action="{{ url_for('count_playlist') }}">
          <input type="hidden" name="folder" value="{{ entry.folder }}">
          <input type="hidden" name="action" value="inc">
          <button type="submit">+</button>
        </form>
      </div>
    </li>
  {% endfor %}
  </ul>
</div>

<form class="upload" id="upload-form" method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data">
  <fieldset>
    {% for name in folders %}
    <label><input type="radio" name="folder" value="{{ name }}" {% if loop.first %}checked{% endif %}> {{ labels[name] }}</label>
    {% endfor %}
  </fieldset>
  <input type="file" name="files" multiple accept=".mp4,.avi,.mkv,.mov" required>
  <br><br>
  <input type="submit" value="Envoyer">
  <div id="progress-wrap">
    <div id="progress-bar"><div id="progress-fill"></div></div>
    <div id="progress-text">0%</div>
  </div>
</form>

<form class="upload newfolder" method="post" action="{{ url_for('create_folder') }}">
  <input type="text" name="name" placeholder="Nom de la nouvelle playlist (ex: noel, halloween)" required>
  <input type="submit" value="Creer">
</form>

<script>
(function () {
  var form = document.getElementById('upload-form');
  if (!form) {
    alert('Erreur JS: formulaire upload-form introuvable dans la page.');
    return;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    try {
      var data = new FormData(form);
      var wrap = document.getElementById('progress-wrap');
      var fill = document.getElementById('progress-fill');
      var text = document.getElementById('progress-text');
      var submitBtn = form.querySelector('input[type=submit]');

      wrap.style.display = 'block';
      fill.style.width = '0%';
      text.textContent = 'Envoi... 0%';
      submitBtn.disabled = true;

      var xhr = new XMLHttpRequest();
      xhr.open('POST', form.action, true);

      xhr.upload.addEventListener('progress', function (evt) {
        if (evt.lengthComputable) {
          var pct = Math.round((evt.loaded / evt.total) * 100);
          fill.style.width = pct + '%';
          text.textContent = pct < 100 ? ('Envoi... ' + pct + '%') : 'Traitement...';
        }
      });

      xhr.addEventListener('load', function () {
        if (xhr.status === 200) {
          fill.style.width = '100%';
          text.textContent = 'Termine, actualisation...';
          window.location.reload();
        } else {
          submitBtn.disabled = false;
          text.textContent = 'Erreur (' + xhr.status + ')';
          alert('Erreur serveur: ' + xhr.status + ' - ' + xhr.responseText);
        }
      });

      xhr.addEventListener('error', function () {
        submitBtn.disabled = false;
        text.textContent = "Erreur reseau pendant l'envoi.";
        alert("Erreur reseau pendant l'envoi (XHR error event).");
      });

      xhr.send(data);
    } catch (err) {
      alert("Erreur JS pendant l'envoi: " + err.message);
    }
  });
})();
</script>

{% for name in folders %}
  <div class="section-header">
    <h2>{{ labels[name] }} ({{ videos[name]|length }})</h2>
    <div class="section-actions">
      {% if videos[name] %}
      <form method="post" action="{{ url_for('clear') }}" onsubmit="return confirm('Supprimer TOUTES les videos de {{ labels[name] }} ({{ videos[name]|length }} fichier(s)) ? Cette action est irreversible.');">
        <input type="hidden" name="folder" value="{{ name }}">
        <button class="clear-all" type="submit">Vider {{ labels[name] }}</button>
      </form>
      {% endif %}
      {% if name not in protected and not videos[name] %}
      <form method="post" action="{{ url_for('delete_folder') }}" onsubmit="return confirm('Supprimer definitivement le dossier {{ labels[name] }} ?');">
        <input type="hidden" name="folder" value="{{ name }}">
        <button class="clear-all" type="submit">Supprimer ce dossier</button>
      </form>
      {% endif %}
    </div>
  </div>
  {% if videos[name] %}
    <ul>
    {% for f in videos[name] %}
      <li>
        <span>{{ f.name }} <span class="size">({{ f.size_mb }} Mo)</span></span>
        <form method="post" action="{{ url_for('delete') }}" onsubmit="return confirm('Supprimer {{ f.name }} ?');">
          <input type="hidden" name="folder" value="{{ name }}">
          <input type="hidden" name="filename" value="{{ f.name }}">
          <button class="del" type="submit">Supprimer</button>
        </form>
      </li>
    {% endfor %}
    </ul>
  {% else %}
    <p class="empty">Aucune video.</p>
  {% endif %}
{% endfor %}

</body>
</html>
"""


def check_auth(username, password):
    return username == USERNAME and password == PASSWORD


def authenticate():
    return Response(
        "Authentification requise.", 401,
        {"WWW-Authenticate": 'Basic realm="memory-vcr"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


def get_disk_usage():
    """Espace disque de la carte SD (mesure sur le dossier utilisateur, qui est
    sur la meme partition que les videos)."""
    usage = shutil.disk_usage(Path.home())
    return {
        "total_gb": round(usage.total / (1024 ** 3), 1),
        "used_gb": round(usage.used / (1024 ** 3), 1),
        "free_gb": round(usage.free / (1024 ** 3), 1),
        "pct_used": round(usage.used / usage.total * 100, 1) if usage.total else 0,
    }


def list_videos(folder: Path):
    if not folder.exists():
        return []
    items = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in EXTENSIONS:
            items.append({"name": f.name, "size_mb": round(f.stat().st_size / 1_000_000, 1)})
    return items


def list_folders():
    """Cree les dossiers par defaut s'ils manquent, puis renvoie la liste de
    tous les dossiers (sous-dossiers directs de BASE_DIR) : les dossiers
    proteges d'abord (publicite, film), puis les playlists creees par
    l'utilisateur par ordre alphabetique."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    for name in DEFAULT_FOLDERS:
        (BASE_DIR / name).mkdir(parents=True, exist_ok=True)
    return sorted(
        (p.name for p in BASE_DIR.iterdir() if p.is_dir()),
        key=lambda n: (n not in PROTECTED_FOLDERS, n.lower())
    )


def load_playlist_config():
    """Charge la programmation de la boucle automatique, et la resynchronise
    avec les dossiers reellement presents sur le disque : les dossiers
    supprimes sont retires de la liste, les dossiers existants mais absents
    de la liste (nouvelle playlist juste creee) sont ajoutes a la fin avec
    un compteur a 0 (non joues tant que l'utilisateur ne l'augmente pas).
    La version resynchronisee est reecrite sur le disque si besoin."""
    existing = set(list_folders())

    config = None
    if PLAYLIST_CONFIG_FILE.exists():
        try:
            data = json.loads(PLAYLIST_CONFIG_FILE.read_text())
            if isinstance(data, list):
                config = [
                    {"folder": e["folder"], "count": int(e.get("count", 0))}
                    for e in data
                    if isinstance(e, dict) and "folder" in e
                ]
        except (OSError, ValueError, KeyError, TypeError):
            config = None

    if config is None:
        config = [dict(e) for e in DEFAULT_PLAYLIST_CONFIG]

    # Retire les entrees dont le dossier n'existe plus.
    config = [e for e in config if e["folder"] in existing]

    # Ajoute les dossiers existants mais pas encore programmes.
    known = {e["folder"] for e in config}
    for name in list_folders():
        if name not in known:
            config.append({"folder": name, "count": 0})

    save_playlist_config(config)
    return config


def save_playlist_config(config):
    PLAYLIST_CONFIG_FILE.write_text(json.dumps(config, indent=2))


def resolve_folder(folder_key: str) -> Path | None:
    """Renvoie le chemin d'un dossier EXISTANT sous BASE_DIR, sans permettre
    d'echappement (path traversal). Ne verifie pas que le dossier existe sur
    le disque, seulement que le chemin resultant est un enfant direct de
    BASE_DIR : appelant responsable de tester target.exists() si besoin."""
    if not folder_key or "/" in folder_key or "\\" in folder_key or folder_key in (".", ".."):
        return None
    base = BASE_DIR.resolve()
    target = (base / folder_key).resolve()
    if target.parent != base:
        return None
    return target


def safe_folder_name(name: str) -> str | None:
    """Nettoie et valide un nom de nouvelle playlist. Renvoie None si le nom
    est vide apres nettoyage ou invalide."""
    if not name:
        return None
    cleaned = secure_filename(name.strip().lower())
    if not cleaned or cleaned in (".", ".."):
        return None
    return cleaned


def safe_target_path(folder_key: str, filename: str) -> Path | None:
    """Renvoie le chemin cible pour un NOUVEAU fichier (upload) : le nom est
    nettoye via secure_filename (accents/espaces/caracteres speciaux retires)."""
    base = resolve_folder(folder_key)
    if base is None:
        return None
    name = secure_filename(filename)
    if not name:
        return None
    target = (base / name).resolve()
    if target.parent != base:
        return None
    return target


def safe_existing_path(folder_key: str, filename: str) -> Path | None:
    """Renvoie le chemin d'un fichier EXISTANT (suppression) sans modifier son
    nom (les fichiers deposes via scp peuvent avoir accents/espaces/parentheses).
    Verifie seulement qu'il n'y a pas d'echappement du dossier (path traversal)."""
    base = resolve_folder(folder_key)
    if base is None:
        return None
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        return None
    target = (base / filename).resolve()
    if target.parent != base:
        return None
    return target


@app.route("/")
@requires_auth
def index():
    folders = list_folders()
    videos = {name: list_videos(BASE_DIR / name) for name in folders}
    labels = {name: FOLDER_LABELS.get(name, name.capitalize()) for name in folders}
    return render_template_string(
        PAGE,
        folders=folders,
        videos=videos,
        labels=labels,
        protected=PROTECTED_FOLDERS,
        disk=get_disk_usage(),
        playlist_config=load_playlist_config(),
    )


@app.route("/upload", methods=["POST"])
@requires_auth
def upload():
    folder_key = request.form.get("folder", "")
    files = request.files.getlist("files")

    target_folder = resolve_folder(folder_key)
    if target_folder is None:
        return jsonify(ok=False, message="Dossier invalide."), 400

    target_folder.mkdir(parents=True, exist_ok=True)

    saved, skipped = 0, []
    for file in files:
        if not file or not file.filename:
            continue
        ext = Path(file.filename).suffix.lower()
        if ext not in EXTENSIONS:
            skipped.append(file.filename)
            continue
        target = safe_target_path(folder_key, file.filename)
        if target is None:
            skipped.append(file.filename)
            continue
        file.save(target)
        saved += 1

    msg = f"{saved} fichier(s) envoye(s) dans '{folder_key}'."
    if skipped:
        msg += f" Ignores (extension non supportee ou nom invalide) : {', '.join(skipped)}."
    flash(msg)
    return jsonify(ok=True, saved=saved, skipped=skipped, message=msg)


@app.route("/delete", methods=["POST"])
@requires_auth
def delete():
    folder_key = request.form.get("folder", "")
    filename = request.form.get("filename", "")
    target = safe_existing_path(folder_key, filename)
    if target is None or not target.exists():
        flash("Fichier introuvable.")
        return redirect(url_for("index"))
    target.unlink()
    flash(f"'{filename}' supprime de '{folder_key}'.")
    return redirect(url_for("index"))


@app.route("/clear", methods=["POST"])
@requires_auth
def clear():
    folder_key = request.form.get("folder", "")
    folder = resolve_folder(folder_key)
    if folder is None:
        flash("Dossier invalide.")
        return redirect(url_for("index"))

    count = 0
    if folder.exists():
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in EXTENSIONS:
                f.unlink()
                count += 1

    flash(f"{count} fichier(s) supprime(s) de '{folder_key}'.")
    return redirect(url_for("index"))


@app.route("/create_folder", methods=["POST"])
@requires_auth
def create_folder():
    raw_name = request.form.get("name", "")
    name = safe_folder_name(raw_name)
    if name is None:
        flash("Nom de playlist invalide.")
        return redirect(url_for("index"))

    target = resolve_folder(name)
    if target is None:
        flash("Nom de playlist invalide.")
        return redirect(url_for("index"))

    if target.exists():
        flash(f"Le dossier '{name}' existe deja.")
        return redirect(url_for("index"))

    target.mkdir(parents=True)
    flash(f"Playlist '{name}' creee. Elle est disponible pour l'upload, mais n'est PAS jouee automatiquement en boucle.")
    return redirect(url_for("index"))


@app.route("/delete_folder", methods=["POST"])
@requires_auth
def delete_folder():
    folder_key = request.form.get("folder", "")

    if folder_key in PROTECTED_FOLDERS:
        flash(f"Le dossier '{folder_key}' est protege et ne peut pas etre supprime.")
        return redirect(url_for("index"))

    target = resolve_folder(folder_key)
    if target is None or not target.exists() or not target.is_dir():
        flash("Dossier introuvable.")
        return redirect(url_for("index"))

    if list_videos(target):
        flash(f"Le dossier '{folder_key}' n'est pas vide, vide-le d'abord.")
        return redirect(url_for("index"))

    try:
        target.rmdir()
    except OSError:
        flash(f"Impossible de supprimer '{folder_key}' (dossier non vide ?).")
        return redirect(url_for("index"))

    flash(f"Dossier '{folder_key}' supprime.")
    return redirect(url_for("index"))


@app.route("/playlist_config/move", methods=["POST"])
@requires_auth
def move_playlist():
    folder_key = request.form.get("folder", "")
    direction = request.form.get("direction", "")

    config = load_playlist_config()
    idx = next((i for i, e in enumerate(config) if e["folder"] == folder_key), None)
    if idx is None or direction not in ("up", "down"):
        return redirect(url_for("index"))

    swap_with = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_with < len(config):
        config[idx], config[swap_with] = config[swap_with], config[idx]
        save_playlist_config(config)

    return redirect(url_for("index"))


@app.route("/playlist_config/count", methods=["POST"])
@requires_auth
def count_playlist():
    folder_key = request.form.get("folder", "")
    action = request.form.get("action", "")

    config = load_playlist_config()
    entry = next((e for e in config if e["folder"] == folder_key), None)
    if entry is None or action not in ("inc", "dec"):
        return redirect(url_for("index"))

    if action == "inc":
        entry["count"] = min(MAX_PLAYLIST_COUNT, entry["count"] + 1)
    else:
        entry["count"] = max(0, entry["count"] - 1)

    save_playlist_config(config)
    return redirect(url_for("index"))


if __name__ == "__main__":
    if PASSWORD == "CHANGE_ME":
        print("!!! Pense a changer PASSWORD dans ce fichier avant usage reel !!!")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
