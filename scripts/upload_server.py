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

PUB_DIR = Path.home() / "videos" / "publicite"
FILM_DIR = Path.home() / "videos" / "film"
EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}
FOLDERS = {"publicite": PUB_DIR, "film": FILM_DIR}

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
  h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid #333; padding-bottom: .3rem; }
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

<form class="upload" id="upload-form" method="post" action="{{ url_for('upload') }}" enctype="multipart/form-data">
  <fieldset>
    <label><input type="radio" name="folder" value="publicite" checked> Publicite</label>
    <label><input type="radio" name="folder" value="film"> Film</label>
  </fieldset>
  <input type="file" name="files" multiple accept=".mp4,.avi,.mkv,.mov" required>
  <br><br>
  <input type="submit" value="Envoyer">
  <div id="progress-wrap">
    <div id="progress-bar"><div id="progress-fill"></div></div>
    <div id="progress-text">0%</div>
  </div>
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

{% for key, label in [("publicite", "Publicite"), ("film", "Film")] %}
  <h2>{{ label }} ({{ videos[key]|length }})</h2>
  {% if videos[key] %}
    <ul>
    {% for f in videos[key] %}
      <li>
        <span>{{ f.name }} <span class="size">({{ f.size_mb }} Mo)</span></span>
        <form method="post" action="{{ url_for('delete') }}" onsubmit="return confirm('Supprimer {{ f.name }} ?');">
          <input type="hidden" name="folder" value="{{ key }}">
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


def safe_target_path(folder_key: str, filename: str) -> Path | None:
    """Renvoie le chemin cible pour un NOUVEAU fichier (upload) : le nom est
    nettoye via secure_filename (accents/espaces/caracteres speciaux retires)."""
    if folder_key not in FOLDERS:
        return None
    base = FOLDERS[folder_key].resolve()
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
    if folder_key not in FOLDERS:
        return None
    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        return None
    base = FOLDERS[folder_key].resolve()
    target = (base / filename).resolve()
    if target.parent != base:
        return None
    return target


@app.route("/")
@requires_auth
def index():
    videos = {
        "publicite": list_videos(PUB_DIR),
        "film": list_videos(FILM_DIR),
    }
    return render_template_string(PAGE, videos=videos, disk=get_disk_usage())


@app.route("/upload", methods=["POST"])
@requires_auth
def upload():
    folder_key = request.form.get("folder", "")
    files = request.files.getlist("files")

    if folder_key not in FOLDERS:
        return jsonify(ok=False, message="Dossier invalide."), 400

    FOLDERS[folder_key].mkdir(parents=True, exist_ok=True)

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


if __name__ == "__main__":
    if PASSWORD == "CHANGE_ME":
        print("!!! Pense a changer PASSWORD dans ce fichier avant usage reel !!!")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
