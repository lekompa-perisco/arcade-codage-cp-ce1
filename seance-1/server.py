#!/usr/bin/env python3
"""Petit serveur local pour le jeu « Professeur Pile Poil ».

Il fait trois choses :
  1. sert le jeu (http://localhost:8000/arcade_seance1_v2.html) ;
  2. lit ta clé ElevenLabs dans le fichier (ou dossier) .env, SANS jamais l'envoyer au navigateur ;
  3. génère les voix à la demande (audio/<id>.mp3) et enregistre tes textes (texts.json).

Lancer :   python3 server.py
Réglages :  fichier .env à côté de ce script, avec par exemple
    ELEVENLABS_API_KEY=sk_xxxxxxxx
    ELEVENLABS_VOICE_ID=xxxxxxxx      (facultatif : tu peux aussi choisir la voix dans le jeu)
Aucune installation : Python 3 suffit.
"""
import hashlib, json, mimetypes, os, re, shutil, sys, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))
BASE = os.environ.get("ELEVENLABS_BASE", "https://api.elevenlabs.io")
AUDIO = os.path.join(ROOT, "audio")
TEXTS = os.path.join(ROOT, "texts.json")
SETTINGS = os.path.join(ROOT, "settings.json")
MANIFEST = os.path.join(AUDIO, "manifest.json")
KEY_NAMES = ("ELEVENLABS_API_KEY", "ELEVEN_LABS_API_KEY", "ELEVENLABS_KEY", "XI_API_KEY")
VOICE_NAMES = ("ELEVENLABS_VOICE_ID", "ELEVEN_LABS_VOICE_ID", "VOICE_ID")
lock = threading.Lock()


def parse_env_text(txt):
    out = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v.strip()
    return out


def load_env():
    """.env peut être un fichier OU un dossier (on lit alors tous les fichiers qu'il contient)."""
    env = {}
    for base in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(base, ".env")
        paths = []
        if os.path.isfile(p):
            paths = [p]
        elif os.path.isdir(p):
            for dp, _, fs in os.walk(p):
                paths += [os.path.join(dp, f) for f in sorted(fs)]
        for f in paths:
            try:
                txt = open(f, encoding="utf-8-sig").read()
            except Exception:
                continue
            d = parse_env_text(txt)
            if not d and txt.strip() and "\n" not in txt.strip() and " " not in txt.strip():
                d = {"ELEVENLABS_API_KEY": txt.strip()}  # fichier contenant seulement la clé
            for k, v in d.items():
                env.setdefault(k, v)
        if env:
            break
    for k in KEY_NAMES + VOICE_NAMES:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def api_key():
    e = load_env()
    for n in KEY_NAMES:
        if e.get(n):
            return e[n]
    return ""


def read_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def voice_id():
    s = read_json(SETTINGS, {})
    if s.get("voice_id"):
        return s["voice_id"]
    e = load_env()
    for n in VOICE_NAMES:
        if e.get(n):
            return e[n]
    return ""


def settings():
    s = read_json(SETTINGS, {})
    return {"stability": float(s.get("stability", 0.45)), "similarity": float(s.get("similarity", 0.8)),
            "style": float(s.get("style", 0.35)), "model": s.get("model", "eleven_multilingual_v2")}


def sig(vid, model, text):
    return hashlib.sha1((vid + model + text).encode("utf-8")).hexdigest()


def clean(t):
    return str(t).replace("**", "").strip()


def eleven(path, body=None, accept="application/json"):
    key = api_key()
    if not key:
        raise RuntimeError("Clé ElevenLabs introuvable : ajoute ELEVENLABS_API_KEY=... dans le fichier .env")
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": accept})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            if e.code == 429 and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            if e.code in (401, 403):
                raise RuntimeError("ElevenLabs refuse la clé (erreur %d). Vérifie-la dans .env. %s" % (e.code, detail))
            raise RuntimeError("Erreur ElevenLabs %d : %s" % (e.code, detail))
        except urllib.error.URLError as e:
            raise RuntimeError("Impossible de joindre ElevenLabs : %s" % e.reason)


def tts(item_id, text, force=False):
    vid = voice_id()
    if not vid:
        raise RuntimeError("Choisis d'abord une voix (menu « Voix ElevenLabs » dans l'éditeur de textes).")
    st = settings()
    text = clean(text)
    if not text:
        raise RuntimeError("Texte vide.")
    safe = re.sub(r"[^A-Za-z0-9_\-]", "", item_id)
    if not safe:
        raise RuntimeError("Identifiant invalide.")
    with lock:
        man = read_json(MANIFEST, {})
        path = os.path.join(AUDIO, safe + ".mp3")
        s = sig(vid, st["model"], text)
        if not force and os.path.exists(path) and man.get(safe) == s:
            return {"ok": True, "cached": True}
    audio = eleven("/v1/text-to-speech/%s?output_format=mp3_44100_128" % vid, {
        "text": text, "model_id": st["model"],
        "voice_settings": {"stability": st["stability"], "similarity_boost": st["similarity"],
                           "style": st["style"], "use_speaker_boost": True}}, accept="audio/mpeg")
    with lock:
        os.makedirs(AUDIO, exist_ok=True)
        open(path, "wb").write(audio)
        man = read_json(MANIFEST, {})
        man[safe] = s
        write_json(MANIFEST, man)
    return {"ok": True, "cached": False}


def plan(items):
    vid = voice_id()
    st = settings()
    man = read_json(MANIFEST, {})
    res = {"missing": [], "stale": [], "ok": []}
    for k, t in items.items():
        safe = re.sub(r"[^A-Za-z0-9_\-]", "", k)
        if not os.path.exists(os.path.join(AUDIO, safe + ".mp3")):
            res["missing"].append(k)
        elif man.get(safe) != sig(vid, st["model"], clean(t)):
            res["stale"].append(k)
        else:
            res["ok"].append(k)
    return res


def export(dest=None):
    """Prépare un dossier prêt à déployer (dist/) : le jeu + les textes + les voix générées. Sans .env ni serveur."""
    dest = os.path.abspath(dest or os.path.join(ROOT, "dist"))
    if dest in (ROOT, AUDIO) or ROOT.startswith(dest + os.sep) or (os.path.isdir(dest) and os.listdir(dest) and not os.path.exists(os.path.join(dest, "index.html"))):
        raise RuntimeError("Dossier d'export invalide ou non vide : " + dest + " (choisis un dossier vide ou un ancien export).")
    htmls = sorted(f for f in os.listdir(ROOT) if f.endswith(".html"))
    if not htmls:
        raise RuntimeError("Aucun fichier .html trouvé à côté de server.py.")
    texts = read_json(TEXTS, {})
    items = {k: v for k, v in read_json(os.path.join(ROOT, "voix.json"), {}).items() if isinstance(v, str)}
    screen_keys = {c.get("k") for c in texts.get("_custom", []) if c.get("type") == "ecran"}
    for k, v in texts.items():
        if isinstance(v, str) and not k.startswith("ui_") and k not in screen_keys:
            items[k] = v
    pl = plan(items)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "audio"))
    html = open(os.path.join(ROOT, htmls[-1]), encoding="utf-8").read()
    blob = json.dumps(texts, ensure_ascii=False).replace("<", "\\u003c")
    html = re.sub(r'(<script id="texts" type="application/json">)[\s\S]*?(</script>)', lambda m: m.group(1) + blob + m.group(2), html, count=1)
    open(os.path.join(dest, "index.html"), "w", encoding="utf-8").write(html)
    write_json(os.path.join(dest, "texts.json"), texts)
    man = read_json(MANIFEST, {})
    kept = {}
    for k in pl["ok"] + pl["stale"]:
        safe = re.sub(r"[^A-Za-z0-9_\-]", "", k)
        shutil.copy(os.path.join(AUDIO, safe + ".mp3"), os.path.join(dest, "audio", safe + ".mp3"))
        if safe in man:
            kept[safe] = man[safe]
    write_json(os.path.join(dest, "audio", "manifest.json"), kept)
    return {"dest": dest, "voices": len(pl["ok"]) + len(pl["stale"]), "missing": pl["missing"], "stale": pl["stale"]}


ALLOWED_EXT = {".html", ".mp3", ".json", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".woff2", ".ico"}
HIDDEN = {"settings.json", "server.py", "generate_voices.py"}


class H(BaseHTTPRequestHandler):
    server_version = "PileMoil/1.0"

    def log_message(self, *a):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("localhost", "127.0.0.1", "[::1]", "::1")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 5_000_000:
            raise ValueError("trop gros")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "interdit"})
        u = urlparse(self.path)
        p = unquote(u.path)
        if p.startswith("/api/"):
            return self.api_get(p, parse_qs(u.query))
        if p in ("", "/"):
            html = [f for f in os.listdir(ROOT) if f.endswith(".html")]
            if html:
                self.send_response(302)
                self.send_header("Location", "/" + sorted(html)[-1])
                self.end_headers()
                return
        parts = [x for x in p.split("/") if x]
        if any(x.startswith(".") or x == ".." for x in parts) or (parts and parts[-1] in HIDDEN):
            return self._send(404, {"error": "introuvable"})  # jamais .env
        full = os.path.normpath(os.path.join(ROOT, *parts))
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(ROOT + os.sep) or ext not in ALLOWED_EXT or not os.path.isfile(full):
            return self._send(404, {"error": "introuvable"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        return self._send(200, open(full, "rb").read(), ctype)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "interdit"})
        try:
            data = self._body()
            p = urlparse(self.path).path
            if p == "/api/texts":
                if not isinstance(data, dict):
                    raise ValueError("format")
                write_json(TEXTS, data)
                return self._send(200, {"ok": True})
            if p == "/api/tts":
                return self._send(200, tts(str(data.get("id", "")), data.get("text", ""), bool(data.get("force"))))
            if p == "/api/export":
                return self._send(200, export())
            if p == "/api/plan":
                return self._send(200, plan(data.get("items", {})))
            if p == "/api/settings":
                s = read_json(SETTINGS, {})
                for k in ("voice_id", "stability", "similarity", "style", "model"):
                    if k in data:
                        s[k] = data[k]
                write_json(SETTINGS, s)
                return self._send(200, {"ok": True})
        except RuntimeError as e:
            return self._send(502, {"error": str(e)})
        except Exception as e:
            return self._send(400, {"error": "Requête invalide : %s" % e})
        self._send(404, {"error": "introuvable"})

    def api_get(self, p, q):
        try:
            if p == "/api/status":
                has_key = bool(api_key())
                return self._send(200, {"key": has_key, "voice_id": voice_id(), "settings": settings(),
                                        "env_found": any(os.path.exists(os.path.join(b, ".env")) for b in (ROOT, os.path.dirname(ROOT)))})
            if p == "/api/voices":
                d = json.loads(eleven("/v1/voices"))
                out = []
                for v in d.get("voices", []):
                    lab = v.get("labels") or {}
                    out.append({"id": v.get("voice_id"), "name": v.get("name"), "lang": lab.get("language", ""),
                                "desc": lab.get("descriptive", "") or lab.get("description", ""), "preview": v.get("preview_url", "")})
                return self._send(200, {"voices": out})
        except RuntimeError as e:
            return self._send(502, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        self._send(404, {"error": "introuvable"})


if __name__ == "__main__":
    os.makedirs(AUDIO, exist_ok=True)
    if "--export" in sys.argv:
        i = sys.argv.index("--export")
        r = export(sys.argv[i + 1] if len(sys.argv) > i + 1 else None)
        print("Dossier prêt à déployer :", r["dest"])
        print("Voix incluses :", r["voices"])
        if r["missing"]:
            print("ATTENTION, %d phrase(s) sans voix (la voix du navigateur sera utilisée) :" % len(r["missing"]), ", ".join(r["missing"][:10]), "…" if len(r["missing"]) > 10 else "")
        if r["stale"]:
            print("Voix pas à jour (texte modifié depuis la génération) :", ", ".join(r["stale"]))
        sys.exit(0)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    htmls = sorted(f for f in os.listdir(ROOT) if f.endswith(".html"))
    print("Clé ElevenLabs :", "trouvée ✔" if api_key() else "INTROUVABLE ✘ (ajoute ELEVENLABS_API_KEY=... dans .env)")
    print("Voix :", voice_id() or "à choisir dans le jeu (Menu > Script oral)")
    print("Ouvre :  http://localhost:%d/%s" % (PORT, htmls[-1] if htmls else ""))
    print("Arrêt : Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
