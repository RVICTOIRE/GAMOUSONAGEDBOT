import csv
import os
import json
import asyncio
import threading
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, Response
import requests
from flask_cors import CORS
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv('config.env')


# ==== CONSTANTES ====
# Rendre le chemin de la base configurable pour la production (ex: Railway Volume /app/data/signalements.db)
DB_FILE = os.getenv("DB_FILE", "./signalements.db")  # Retour au chemin local
JSON_FILE = os.getenv("JSON_FILE", "./signalements.json")  # Retour au chemin local

# WhatsApp Cloud API (Meta)
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN")  # pour la vérification du webhook
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN")  # token d'accès Graph API
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")  # identifiant du numéro business


def _ensure_parent_dir(path: str) -> None:
    try:
        parent = os.path.dirname(path or "")
        if parent:
            os.makedirs(parent, exist_ok=True)
    except Exception as e:
        print(f"Erreur création dossier parent pour {path}: {e}")


@contextmanager
def get_db_connection():
    _ensure_parent_dir(DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def ensure_db_exists() -> None:
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signalements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_heure TEXT NOT NULL,
                utilisateur TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                photo_id TEXT,
                latitude REAL,
                longitude REAL
            )
        """)
        conn.commit()


def clean_type_string(type_str: str) -> str:
    """Nettoie et normalise les chaînes de type"""
    if not type_str:
        return "Autre"
    
    # Décodage des caractères Unicode échappés
    try:
        # Si c'est déjà une chaîne normale, on la retourne
        if "\\u" not in type_str:
            return type_str
        
        # Décodage des séquences Unicode
        cleaned = type_str.encode('utf-8').decode('unicode_escape')
        return cleaned
    except:
        return type_str

def read_signalements_from_db() -> List[Dict[str, Any]]:
    ensure_db_exists()
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT date_heure, utilisateur, type, message, photo_id, latitude, longitude
            FROM signalements
            ORDER BY date_heure DESC
        """)
        return [
            {
                "Date/Heure": row["date_heure"],
                "Utilisateur": row["utilisateur"],
                "Type": clean_type_string(row["type"]),
                "Message": row["message"],
                "Photo": row["photo_id"] if row["photo_id"] else None,
                "Latitude": row["latitude"],
                "Longitude": row["longitude"],
            }
            for row in cursor.fetchall()
        ]


def append_signalement_to_db(utilisateur: str, type_signalement: str, message: str, latitude: float, longitude: float, photo_id: str = None) -> Dict[str, Any]:
    ensure_db_exists()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO signalements (date_heure, utilisateur, type, message, photo_id, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, utilisateur, type_signalement, message, photo_id, latitude, longitude))
        conn.commit()
    return {
        "Date/Heure": now_str,
        "Utilisateur": utilisateur,
        "Type": type_signalement,
        "Message": message,
        "Photo": photo_id,
        "Latitude": latitude,
        "Longitude": longitude,
    }


def append_signalement_nullable(utilisateur: str, type_signalement: str, message: str, latitude: float | None, longitude: float | None, photo_id: str | None = None) -> Dict[str, Any]:
    ensure_db_exists()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO signalements (date_heure, utilisateur, type, message, photo_id, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_str, utilisateur, type_signalement, message, photo_id, latitude, longitude),
        )
        conn.commit()
    return {
        "Date/Heure": now_str,
        "Utilisateur": utilisateur,
        "Type": type_signalement,
        "Message": message,
        "Photo": photo_id,
        "Latitude": latitude,
        "Longitude": longitude,
    }


def write_json_snapshot(signalements: List[Dict[str, Any]]) -> None:
    _ensure_parent_dir(JSON_FILE)
    with open(JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(signalements, file, ensure_ascii=False, indent=4)


app = Flask(__name__)
CORS(app)

# ==== Initialisation Application Telegram (sans serveur webhook propre) ====
# Déférer la création de l'application Telegram pour éviter les erreurs au boot
telegram_app = None
_tg_started = False
_tg_enabled = os.getenv("START_TG_ON_BOOT", "1").lower() not in ("0", "false", "no")
_tg_loop = None  # boucle asyncio de l'application Telegram

# Lire les variables webhook côté Flask pour éviter les imports croisés
TG_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
TG_WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()
TG_WEBHOOK_PATH = (os.getenv("WEBHOOK_PATH", "/webhook") or "").strip() or "/webhook"

# Normalisation de l'URL complète
def _compute_full_webhook_url(base_url: str, path: str) -> str | None:
    if not base_url:
        return None
    base = base_url.strip()
    # Supprimer caractères non imprimables courants \r / \n / \t
    base = base.replace("\r", "").replace("\n", "").replace("\t", "")
    path_clean = (path or "/webhook").strip()
    path_clean = path_clean.replace("\r", "").replace("\n", "").replace("\t", "")
    if not path_clean.startswith("/"):
        path_clean = "/" + path_clean
    # Éviter de doubler le path si déjà présent
    if base.endswith(path_clean):
        return base
    return base.rstrip("/") + path_clean


print(f"🔧 Configuration Telegram: enabled={_tg_enabled}, webhook_url={TG_WEBHOOK_URL}, secret={'***' if TG_WEBHOOK_SECRET else 'None'}")

async def _start_telegram_app() -> None:
    global telegram_app, _tg_loop
    print("🚀 Démarrage de l'application Telegram...")
    if telegram_app is None:
        # Import paresseux pour éviter erreurs d'import au boot
        from gamousonagedbot import build_application as build_telegram_application
        print("📦 Construction de l'application Telegram...")
        telegram_app = build_telegram_application()
    print("⚡ Initialisation de l'application Telegram...")
    await telegram_app.initialize()
    print("▶️ Démarrage de l'application Telegram...")
    await telegram_app.start()
    _tg_loop = asyncio.get_running_loop()
    # Enregistrer le webhook côté Telegram si une URL publique est fournie
    full_url = _compute_full_webhook_url(TG_WEBHOOK_URL, TG_WEBHOOK_PATH)
    if full_url:
        try:
            print(f"🌐 Enregistrement du webhook: {full_url}")
            await telegram_app.bot.set_webhook(
                url=full_url,
                secret_token=TG_WEBHOOK_SECRET,
                drop_pending_updates=True,
            )
            print(f"✅ Webhook Telegram enregistré: {full_url}")
        except Exception as e:
            print(f"⚠️ Impossible d'enregistrer le webhook Telegram: {e}")
    else:
        print("⚠️ WEBHOOK_URL non défini, webhook non enregistré")

def _run_telegram_app_bg() -> None:
    print("🔄 Lancement du thread Telegram...")
    try:
        asyncio.run(_start_telegram_app())
    except Exception as e:
        print(f"❌ Erreur lors du démarrage Telegram: {e}")

def _ensure_tg_started() -> None:
    global _tg_started
    if _tg_started or not _tg_enabled:
        return
    print("🎯 Démarrage du bot Telegram...")
    _tg_started = True
    threading.Thread(target=_run_telegram_app_bg, daemon=True).start()

# Démarrer le bot automatiquement au démarrage de Flask
if _tg_enabled:
    print("🚀 Démarrage automatique du bot Telegram...")
    _ensure_tg_started()


@app.get("/")
def index() -> Response:
    # S'assurer que le bot démarre (si activé) à la première requête
    _ensure_tg_started()
    return (
        "Signalements SONAGED API is running. Visit /carte or /dashboard.",
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


@app.route("/health", methods=["GET", "HEAD"])
def health() -> Response:
    _ensure_tg_started()
    return ("ok", 200, {"Content-Type": "text/plain; charset=utf-8"})

# Alias supplémentaires pour compatibilité plateformes
@app.route("/hc", methods=["GET", "HEAD"])
def health_hc() -> Response:
    return ("ok", 200, {"Content-Type": "text/plain; charset=utf-8"})

@app.route("/_health", methods=["GET", "HEAD"])
def health_alt() -> Response:
    return ("ok", 200, {"Content-Type": "text/plain; charset=utf-8"})


@app.get("/carte")
def carte() -> Response:
    # Sert `carte_signalements.html`
    return send_from_directory(".", "carte_signalements.html")


@app.get("/form")
def form() -> Response:
    # Sert `signalement.html`
    return send_from_directory(".", "signalement.html")


@app.get("/signalements.json")
def get_signalements_json() -> Response:
    # 1) Tenter de servir le fichier JSON configuré
    try:
        if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"/signalements.json servi depuis JSON_FILE: {JSON_FILE} (n={len(data)})")
            resp = jsonify(data)
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp
    except Exception as e:
        print(f"Erreur lecture JSON_FILE ({JSON_FILE}): {e}")
    
    # 2) Compatibilité: tenter l'ancien fichier à la racine
    legacy_path = os.path.join(".", "signalements.json")
    try:
        if os.path.exists(legacy_path) and os.path.getsize(legacy_path) > 0:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"/signalements.json servi depuis legacy: {legacy_path} (n={len(data)})")
            resp = jsonify(data)
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp
    except Exception as e:
        print(f"Erreur lecture legacy JSON ({legacy_path}): {e}")

    # 3) Repli: lire depuis la DB et réécrire le snapshot
    signalements = read_signalements_from_db()
    try:
        write_json_snapshot(signalements)
    except Exception as e:
        print(f"Erreur écriture JSON: {e}")
        pass
    print(f"/signalements.json repli DB (n={len(signalements)}) et snapshot réécrit vers {JSON_FILE}")
    resp = jsonify(signalements)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.get("/debug/json")
def debug_json_meta() -> Response:
    legacy_path = os.path.join(".", "signalements.json")
    def stat_info(path: str):
        try:
            return {
                "exists": os.path.exists(path),
                "size": os.path.getsize(path) if os.path.exists(path) else 0,
                "mtime": os.path.getmtime(path) if os.path.exists(path) else None,
            }
        except Exception as e:
            return {"error": str(e)}
    info = {
        "JSON_FILE": JSON_FILE,
        "JSON_FILE_stat": stat_info(JSON_FILE),
        "legacy_path": legacy_path,
        "legacy_stat": stat_info(legacy_path),
    }
    # Essayer de charger quelques entrées pour aperçu
    samples = []
    try:
        if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            samples = data[:3]
            info["count"] = len(data)
            info["source"] = "JSON_FILE"
        elif os.path.exists(legacy_path) and os.path.getsize(legacy_path) > 0:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            samples = data[:3]
            info["count"] = len(data)
            info["source"] = "legacy"
        else:
            data = read_signalements_from_db()
            samples = data[:3]
            info["count"] = len(data)
            info["source"] = "db"
    except Exception as e:
        info["load_error"] = str(e)
    return jsonify({"meta": info, "samples": samples})


ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

def require_admin() -> bool:
    if not ADMIN_TOKEN:
        return True
    token = request.headers.get("X-Admin-Token") or request.args.get("token")
    return token == ADMIN_TOKEN

@app.post("/api/refresh-json")
def refresh_json() -> Response:
    """Force la régénération du fichier signalements.json"""
    if not require_admin():
        return jsonify({"status": "forbidden"}), 403
    try:
        signalements = read_signalements_from_db()
        write_json_snapshot(signalements)
        return jsonify({"status": "ok", "message": f"JSON régénéré avec {len(signalements)} signalements"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.delete("/api/signalements/<int:signalement_id>")
def delete_signalement(signalement_id: int) -> Response:
    """Supprime un signalement par ID et régénère le JSON"""
    if not require_admin():
        return jsonify({"status": "forbidden"}), 403
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT id FROM signalements WHERE id = ?", (signalement_id,))
            if not cursor.fetchone():
                return jsonify({"status": "error", "message": "Signalement non trouvé"}), 404
            conn.execute("DELETE FROM signalements WHERE id = ?", (signalement_id,))
            conn.commit()
            signalements = read_signalements_from_db()
            write_json_snapshot(signalements)
            return jsonify({"status": "ok", "message": "Signalement supprimé et JSON mis à jour"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.post("/api/signalements/delete")
def delete_signalement_by_criteria() -> Response:
    """Supprime un signalement par critères (date, utilisateur, message) et régénère le JSON"""
    if not require_admin():
        return jsonify({"status": "forbidden"}), 403
    
    payload = request.get_json(silent=True) or {}
    date_heure = payload.get("date_heure")
    utilisateur = payload.get("utilisateur")
    message = payload.get("message")
    type_signalement = payload.get("type")
    
    if not any([date_heure, utilisateur, message, type_signalement]):
        return jsonify({"status": "error", "message": "Au moins un critère requis (date_heure, utilisateur, message, type)"}), 400
    
    try:
        # Construire la requête dynamiquement
        conditions = []
        params = []
        
        if date_heure:
            conditions.append("date_heure = ?")
            params.append(date_heure)
        if utilisateur:
            conditions.append("utilisateur = ?")
            params.append(utilisateur)
        if message:
            conditions.append("message = ?")
            params.append(message)
        if type_signalement:
            conditions.append("type = ?")
            params.append(type_signalement)
        
        where_clause = " AND ".join(conditions)
        
        with get_db_connection() as conn:
            # Vérifier si le signalement existe
            cursor = conn.execute(f"SELECT id FROM signalements WHERE {where_clause}", params)
            if not cursor.fetchone():
                return jsonify({"status": "error", "message": "Signalement non trouvé"}), 404
            
            # Supprimer le signalement
            conn.execute(f"DELETE FROM signalements WHERE {where_clause}", params)
            conn.commit()
            
            # Régénérer le JSON
            signalements = read_signalements_from_db()
            write_json_snapshot(signalements)
            
            return jsonify({
                "status": "ok", 
                "message": "Signalement supprimé et JSON mis à jour",
                "criteria": {
                    "date_heure": date_heure,
                    "utilisateur": utilisateur,
                    "message": message,
                    "type": type_signalement
                }
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.post("/api/signalements/delete-multiple")
def delete_multiple_signalements() -> Response:
    """Supprime plusieurs signalements par critères et régénère le JSON"""
    if not require_admin():
        return jsonify({"status": "forbidden"}), 403
    
    payload = request.get_json(silent=True) or {}
    date_heure = payload.get("date_heure")
    utilisateur = payload.get("utilisateur")
    type_signalement = payload.get("type")
    
    if not any([date_heure, utilisateur, type_signalement]):
        return jsonify({"status": "error", "message": "Au moins un critère requis (date_heure, utilisateur, type)"}), 400
    
    try:
        # Construire la requête dynamiquement
        conditions = []
        params = []
        
        if date_heure:
            conditions.append("date_heure = ?")
            params.append(date_heure)
        if utilisateur:
            conditions.append("utilisateur = ?")
            params.append(utilisateur)
        if type_signalement:
            conditions.append("type = ?")
            params.append(type_signalement)
        
        where_clause = " AND ".join(conditions)
        
        with get_db_connection() as conn:
            # Compter les signalements à supprimer
            cursor = conn.execute(f"SELECT COUNT(*) FROM signalements WHERE {where_clause}", params)
            count = cursor.fetchone()[0]
            
            if count == 0:
                return jsonify({"status": "error", "message": "Aucun signalement trouvé"}), 404
            
            # Supprimer les signalements
            conn.execute(f"DELETE FROM signalements WHERE {where_clause}", params)
            conn.commit()
            
            # Régénérer le JSON
            signalements = read_signalements_from_db()
            write_json_snapshot(signalements)
            
            return jsonify({
                "status": "ok", 
                "message": f"{count} signalement(s) supprimé(s) et JSON mis à jour",
                "deleted_count": count,
                "criteria": {
                    "date_heure": date_heure,
                    "utilisateur": utilisateur,
                    "type": type_signalement
                }
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==== Webhook Telegram → Transfert vers l'application PTB ====
@app.post("/webhook")
def telegram_webhook() -> Response:
    print("🔔 Webhook appelé - Headers:", dict(request.headers))
    print("🔔 Webhook payload:", request.get_json(silent=True))
    
    # Vérification du secret (si configuré)
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if TG_WEBHOOK_SECRET and provided != TG_WEBHOOK_SECRET:
        print("❌ Secret invalide - fourni:", provided, "attendu:", TG_WEBHOOK_SECRET)
        return jsonify({"status": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    try:
        # Import paresseux pour éviter dépendance Telegram à l'import
        if telegram_app is None or _tg_loop is None:
            print("❌ Application Telegram non disponible ou boucle absente")
            return jsonify({"status": "unavailable"}), 503
        from telegram import Update as TGUpdate
        update = TGUpdate.de_json(payload, telegram_app.bot)
        print("✅ Update parsé:", update)
        # Soumettre le traitement sur la boucle PTB
        fut = asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), _tg_loop)
        # Optionnel: vérifier les exceptions rapidement
        try:
            fut.result(timeout=0)
        except Exception:
            pass
        print("✅ Update soumis au processeur PTB")
    except Exception as e:
        print("❌ Erreur traitement update:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 400

    print("✅ Webhook traité avec succès")
    return jsonify({"status": "ok"})


@app.get("/webhook/whatsapp")
def whatsapp_verify() -> Response:
    """Verification webhook pour Meta/WhatsApp (GET challenge)"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    print(f"🔍 WhatsApp verification - mode: {mode}, token: {token}, expected: {WA_VERIFY_TOKEN}")
    
    if mode == "subscribe" and token and WA_VERIFY_TOKEN and token == WA_VERIFY_TOKEN:
        print(f"✅ WhatsApp verification successful - returning challenge: {challenge}")
        return Response(challenge, status=200, content_type="text/plain; charset=utf-8")
    
    print(f"❌ WhatsApp verification failed - mode: {mode}, token match: {token == WA_VERIFY_TOKEN if token and WA_VERIFY_TOKEN else 'missing'}")
    return Response("forbidden", status=403, content_type="text/plain; charset=utf-8")


@app.post("/webhook/whatsapp")
def whatsapp_webhook() -> Response:
    """Réception des messages WhatsApp via Cloud API"""
    print("🔔 WhatsApp webhook POST appelé")
    print(f"🔔 Headers: {dict(request.headers)}")
    
    try:
        payload = request.get_json(silent=True) or {}
        print(f"🔔 Payload: {payload}")
        
        # Parcourir la structure typique de Meta
        entries = payload.get("entry") or []
        print(f"🔔 Entries trouvées: {len(entries)}")
        
        created_count = 0
        response_count = 0
        for entry in entries:
            changes = entry.get("changes") or []
            print(f"🔔 Changes dans entry: {len(changes)}")
            for change in changes:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                contacts = value.get("contacts") or []
                print(f"🔔 Messages trouvés: {len(messages)}, Contacts: {len(contacts)}")
                
                contact_name = None
                if contacts:
                    profile = (contacts[0] or {}).get("profile") or {}
                    contact_name = profile.get("name")
                for msg in messages:
                    from_wa = msg.get("from")  # numéro MSISDN
                    msg_type = msg.get("type")
                    print(f"🔔 Message de {from_wa}, type: {msg_type}")
                    
                    utilisateur = contact_name or from_wa or "WhatsApp"
                    # Conversation state machine
                    _wa_handle_incoming_message(from_wa, utilisateur, msg)
                    response_count += 1
                    print(f"🔔 Réponse envoyée à {from_wa}")
                    
                    # Data extraction for passive recording (optional)
                    type_signalement = "WhatsApp"
                    message_text = None
                    photo_id = None
                    latitude = None
                    longitude = None
                    if msg_type == "text":
                        message_text = (msg.get("text") or {}).get("body")
                    elif msg_type == "location":
                        loc = msg.get("location") or {}
                        latitude = loc.get("latitude")
                        longitude = loc.get("longitude")
                        message_text = loc.get("name") or "Localisation"
                    elif msg_type == "image":
                        # On enregistre une référence d'image (id media)
                        image = msg.get("image") or {}
                        photo_id = image.get("id")
                        message_text = image.get("caption") or "Image"
                    else:
                        # autres types ignorés pour MVP
                        continue
                    created = append_signalement_nullable(
                        utilisateur=utilisateur,
                        type_signalement=type_signalement,
                        message=message_text or "",
                        latitude=latitude,
                        longitude=longitude,
                        photo_id=photo_id,
                    )
                    created_count += 1
        # Mettre à jour le JSON
        try:
            write_json_snapshot(read_signalements_from_db())
        except Exception:
            pass
        print(f"🔔 Résumé: {created_count} créés, {response_count} réponses")
        return jsonify({"status": "ok", "created": created_count, "responded": response_count})
    except Exception as e:
        print(f"❌ Erreur WhatsApp webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.get("/debug/signalements")
def debug_signalements() -> Response:
    """Endpoint de debug pour vérifier les données"""
    try:
        signalements = read_signalements_from_db()
        return jsonify({
            "count": len(signalements),
            "data": signalements,
            "db_file": DB_FILE,
            "db_exists": os.path.exists(DB_FILE)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/signalements")
def api_list_signalements() -> Response:
    signalements = read_signalements_from_db()
    return jsonify(signalements)


@app.post("/api/signalements")
def api_create_signalement() -> Response:
    payload = request.get_json(silent=True) or {}

    utilisateur = payload.get("Utilisateur")
    type_signalement = payload.get("Type")
    message = payload.get("Message")
    photo_id = payload.get("Photo")  # Nouveau champ pour la photo
    latitude_raw = payload.get("Latitude")
    longitude_raw = payload.get("Longitude")

    # Validation minimale
    errors = {}
    if not utilisateur:
        errors["Utilisateur"] = "Champ requis"
    if not type_signalement:
        errors["Type"] = "Champ requis"
    if not message:
        errors["Message"] = "Champ requis"

    try:
        latitude = float(latitude_raw) if latitude_raw is not None else None
    except Exception:
        errors["Latitude"] = "Doit être un nombre"
        latitude = None

    try:
        longitude = float(longitude_raw) if longitude_raw is not None else None
    except Exception:
        errors["Longitude"] = "Doit être un nombre"
        longitude = None

    if latitude is None or longitude is None:
        errors["location"] = "Latitude et Longitude sont requis"

    if errors:
        return jsonify({"status": "error", "errors": errors}), 400

    created = append_signalement_to_db(
        utilisateur=utilisateur,
        type_signalement=type_signalement,
        message=message,
        latitude=latitude,
        longitude=longitude,
        photo_id=photo_id,
    )

    # Met à jour le snapshot JSON pour compatibilité avec la carte statique
    try:
        write_json_snapshot(read_signalements_from_db())
    except Exception:
        pass

    return jsonify({"status": "ok", "signalement": created}), 201


@app.get("/api/admin/signalements")
def admin_list_signalements() -> Response:
    if not require_admin():
        return jsonify({"status": "forbidden"}), 403
    # Lire depuis le JSON comme la carte/tableau de bord
    try:
        if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            resp = jsonify([
                {"id": None, **item} for item in data
            ])
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp
    except Exception as e:
        print(f"Erreur lecture JSON_FILE ({JSON_FILE}) pour admin: {e}")
    # Fallback legacy
    legacy_path = os.path.join(".", "signalements.json")
    try:
        if os.path.exists(legacy_path) and os.path.getsize(legacy_path) > 0:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            resp = jsonify([
                {"id": None, **item} for item in data
            ])
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            return resp
    except Exception as e:
        print(f"Erreur lecture legacy JSON ({legacy_path}) pour admin: {e}")
    # Repli DB si JSON absent
    ensure_db_exists()
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, date_heure, utilisateur, type, message, photo_id, latitude, longitude
            FROM signalements
            ORDER BY date_heure DESC
            """
        )
        data = [
            {
                "id": row["id"],
                "Date/Heure": row["date_heure"],
                "Utilisateur": row["utilisateur"],
                "Type": row["type"],
                "Message": row["message"],
                "Photo": row["photo_id"] if row["photo_id"] else None,
                "Latitude": row["latitude"],
                "Longitude": row["longitude"],
            }
            for row in cursor.fetchall()
        ]
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


def read_signalements_for_display() -> List[Dict[str, Any]]:
    """Lit les signalements comme la carte/admin: JSON d'abord, DB en repli."""
    # 1) JSON principal
    try:
        if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lecture JSON_FILE ({JSON_FILE}) pour display: {e}")
    # 2) JSON legacy
    legacy_path = os.path.join(".", "signalements.json")
    try:
        if os.path.exists(legacy_path) and os.path.getsize(legacy_path) > 0:
            with open(legacy_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Erreur lecture legacy JSON ({legacy_path}) pour display: {e}")
    # 3) Repli DB
    return read_signalements_from_db()


def compute_stats_from_db() -> Dict[str, Any]:
    entries = read_signalements_for_display()
    total = len(entries)
    by_type: Dict[str, int] = {}
    by_day: Dict[str, int] = {}

    for item in entries:
        type_value = item.get("Type") or "Inconnu"
        by_type[type_value] = by_type.get(type_value, 0) + 1

        date_raw = item.get("Date/Heure") or ""
        day_key = None
        if date_raw:
            try:
                dt = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                day_key = dt.strftime("%Y-%m-%d")
            except Exception:
                day_key = date_raw[:10]
        else:
            day_key = "inconnu"
        by_day[day_key] = by_day.get(day_key, 0) + 1

    by_day_sorted = dict(sorted(by_day.items(), key=lambda kv: kv[0]))

    def sort_key(item: Dict[str, Any]):
        try:
            return datetime.strptime(item.get("Date/Heure", ""), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    latest_entries = sorted(entries, key=sort_key, reverse=True)[:20]

    return {
        "total": total,
        "by_type": by_type,
        "by_day": by_day_sorted,
        "latest": latest_entries,
    }


@app.get("/api/stats")
def api_stats() -> Response:
    stats = compute_stats_from_db()
    resp = jsonify(stats)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp


@app.get("/dashboard")
def dashboard() -> Response:
    return send_from_directory(".", "dashboard.html")

@app.get("/admin")
def admin_page() -> Response:
    return send_from_directory(".", "admin.html")


@app.get("/debug/db-vs-json")
def debug_db_vs_json() -> Response:
    """Compare la DB et le JSON pour voir les différences"""
    try:
        # Lire depuis la DB
        db_signalements = read_signalements_from_db()
        
        # Lire depuis le JSON
        json_signalements = []
        if os.path.exists(JSON_FILE) and os.path.getsize(JSON_FILE) > 0:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                json_signalements = json.load(f)
        
        # Comparer
        db_count = len(db_signalements)
        json_count = len(json_signalements)
        
        # Trouver les signalements en DB mais pas en JSON
        db_dates = {s["Date/Heure"] for s in db_signalements}
        json_dates = {s["Date/Heure"] for s in json_signalements}
        missing_in_json = db_dates - json_dates
        
        # Signalements manquants dans le JSON
        missing_signalements = [s for s in db_signalements if s["Date/Heure"] in missing_in_json]
        
        return jsonify({
            "db_count": db_count,
            "json_count": json_count,
            "missing_in_json_count": len(missing_in_json),
            "missing_in_json": missing_signalements,
            "db_file": DB_FILE,
            "json_file": JSON_FILE,
            "db_exists": os.path.exists(DB_FILE),
            "json_exists": os.path.exists(JSON_FILE)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/debug/all-dbs")
def debug_all_dbs() -> Response:
    """Vérifie tous les emplacements possibles de la base de données"""
    possible_dbs = [
        "/app/data/signalements.db",
        "./signalements.db", 
        "signalements.db",
        "/tmp/signalements.db"
    ]
    
    results = {}
    for db_path in possible_dbs:
        try:
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.execute("SELECT COUNT(*) as count FROM signalements")
                count = cursor.fetchone()[0]
                cursor = conn.execute("SELECT date_heure, utilisateur, type FROM signalements ORDER BY date_heure DESC LIMIT 5")
                recent = [{"date": row[0], "user": row[1], "type": row[2]} for row in cursor.fetchall()]
                conn.close()
                results[db_path] = {
                    "exists": True,
                    "count": count,
                    "recent": recent,
                    "size": os.path.getsize(db_path)
                }
            else:
                results[db_path] = {"exists": False}
        except Exception as e:
            results[db_path] = {"exists": False, "error": str(e)}
    
    return jsonify({
        "current_db_file": DB_FILE,
        "databases": results
    })


#########################
# WhatsApp Helpers/State #
#########################

# Etat en mémoire: { wa_number: {state: str, type: str|None, text: str|None, photo_id: str|None} }
WA_SESSIONS: Dict[str, Dict[str, Any]] = {}

def _wa_send_message(wa_to: str, text: str, buttons: list[dict] | None = None) -> None:
    if not (WA_ACCESS_TOKEN and WA_PHONE_NUMBER_ID):
        print(f"❌ WhatsApp config manquante: ACCESS_TOKEN={bool(WA_ACCESS_TOKEN)}, PHONE_ID={bool(WA_PHONE_NUMBER_ID)}")
        return
    url = f"https://graph.facebook.com/v20.0/{WA_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WA_ACCESS_TOKEN}", "Content-Type": "application/json"}
    data: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": wa_to,
        "type": "text",
        "text": {"body": text},
    }
    # Quick replies via interactive buttons
    if buttons:
        data = {
            "messaging_product": "whatsapp",
            "to": wa_to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text[:1024]},
                "action": {"buttons": buttons[:3]},
            },
        }
    try:
        print(f"📤 Envoi WhatsApp à {wa_to}: {text}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"📤 Réponse Meta: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erreur envoi WhatsApp: {e}")

def _wa_quick_button(title: str, payload: str) -> dict:
    return {"type": "reply", "reply": {"id": payload, "title": title[:20]}}

def _wa_handle_incoming_message(wa_from: str, user_name: str, msg: Dict[str, Any]) -> None:
    session = WA_SESSIONS.get(wa_from) or {"state": "NEW", "type": None, "text": None, "photo_id": None}
    msg_type = msg.get("type")
    text_body = (msg.get("text") or {}).get("body") if msg_type == "text" else None
    interactive = msg.get("interactive")
    button_reply_id = None
    if interactive and interactive.get("type") == "button_reply":
        button_reply_id = (interactive.get("button_reply") or {}).get("id")

    state = session.get("state")
    print(f"🤖 WhatsApp session {wa_from}: state={state}, msg_type={msg_type}, text={text_body}, button={button_reply_id}")

    if state == "NEW":
        # Start: propose type
        session["state"] = "CHOIX"
        WA_SESSIONS[wa_from] = session
        _wa_send_message(
            wa_from,
            "Que souhaitez-vous signaler ?",
            buttons=[
                _wa_quick_button("📍 Dépôt", "TYPE_DEPOT"),
                _wa_quick_button("🗑 Bac plein", "TYPE_BAC"),
                _wa_quick_button("🔹 Autres", "TYPE_AUTRES"),
            ],
        )
        return

    if state == "CHOIX":
        if button_reply_id in ("TYPE_DEPOT", "TYPE_BAC", "TYPE_AUTRES"):
            session["type"] = {
                "TYPE_DEPOT": "📍 Dépôt",
                "TYPE_BAC": "🗑 Bac plein",
                "TYPE_AUTRES": "🔹 Autres",
            }[button_reply_id]
            session["state"] = "TEXTE"
            WA_SESSIONS[wa_from] = session
            _wa_send_message(wa_from, "Merci. Veuillez préciser les détails du signalement.")
        else:
            _wa_send_message(wa_from, "Choisissez une option en appuyant sur un bouton.")
        return

    if state == "TEXTE":
        if text_body:
            session["text"] = text_body
            session["state"] = "CHOIX_MEDIA"
            WA_SESSIONS[wa_from] = session
            _wa_send_message(
                wa_from,
                "Vous pouvez d'abord ajouter une photo, puis envoyer votre localisation.",
                buttons=[
                    _wa_quick_button("📷 Joindre une photo", "MEDIA_PHOTO"),
                    _wa_quick_button("📍 Localisation", "MEDIA_LOC"),
                ],
            )
        else:
            _wa_send_message(wa_from, "Envoyez le texte du signalement.")
        return

    if state == "CHOIX_MEDIA":
        # Handle button choice or incoming media/location
        if button_reply_id == "MEDIA_PHOTO":
            _wa_send_message(wa_from, "Envoyez une image (joignez une photo à ce chat).")
            session["state"] = "ATTENTE_PHOTO"
            WA_SESSIONS[wa_from] = session
            return
        if button_reply_id == "MEDIA_LOC":
            _wa_send_message(wa_from, "Partagez votre localisation via WhatsApp.")
            session["state"] = "ATTENTE_LOC"
            WA_SESSIONS[wa_from] = session
            return
        if msg_type == "image":
            image = msg.get("image") or {}
            session["photo_id"] = image.get("id")
            session["state"] = "ATTENTE_LOC"
            WA_SESSIONS[wa_from] = session
            _wa_send_message(wa_from, "✅ Photo ajoutée. Maintenant, envoyez votre localisation.")
            return
        if msg_type == "location":
            loc = msg.get("location") or {}
            _wa_finalize_report(wa_from, user_name, session, loc.get("latitude"), loc.get("longitude"))
            return
        _wa_send_message(wa_from, "Choisissez une option ou envoyez la photo/la localisation.")
        return

    if state in ("ATTENTE_PHOTO", "ATTENTE_LOC"):
        if msg_type == "image":
            image = msg.get("image") or {}
            session["photo_id"] = image.get("id")
            session["state"] = "ATTENTE_LOC"
            WA_SESSIONS[wa_from] = session
            _wa_send_message(wa_from, "✅ Photo ajoutée. Maintenant, envoyez votre localisation.")
            return
        if msg_type == "location":
            loc = msg.get("location") or {}
            _wa_finalize_report(wa_from, user_name, session, loc.get("latitude"), loc.get("longitude"))
            return
        _wa_send_message(wa_from, "Envoyez la photo ou la localisation.")
        return

def _wa_finalize_report(wa_from: str, user_name: str, session: Dict[str, Any], lat: Any, lon: Any) -> None:
    try:
        latitude = float(lat) if lat is not None else None
        longitude = float(lon) if lon is not None else None
    except Exception:
        latitude = None
        longitude = None
    created = append_signalement_nullable(
        utilisateur=user_name or wa_from,
        type_signalement=session.get("type") or "WhatsApp",
        message=session.get("text") or "",
        latitude=latitude,
        longitude=longitude,
        photo_id=session.get("photo_id"),
    )
    try:
        write_json_snapshot(read_signalements_from_db())
    except Exception:
        pass
    WA_SESSIONS.pop(wa_from, None)
    _wa_send_message(wa_from, "✅ Signalement complet enregistré !")


if __name__ == "__main__":
    ensure_db_exists()
    port = int(os.getenv("PORT", "5000"))
    print(f"🚀 API Flask SONAGED active sur http://127.0.0.1:{port} …")
    app.run(host="0.0.0.0", port=port, debug=True)

