#!/usr/bin/env python3

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging
import threading
from datetime import datetime

from run_daily_scraping import run_daily_scraping
from src.utils.logging_config import configure_logging

# Application Flask (optionnelle si vous voulez un endpoint HTTP)
app = Flask(__name__)
APP_VERSION = "1.1.1"
configure_logging()
logging.getLogger('apscheduler').setLevel(logging.INFO)

# Concurrency guard
_scrape_lock = threading.Lock()
_is_running = False


def _run_scrape_with_guard():
    global _is_running
    if not _scrape_lock.acquire(blocking=False):
        # Already running
        return False
    _is_running = True
    try:
        run_daily_scraping()
    finally:
        _is_running = False
        _scrape_lock.release()
    return True


def scraping_job():
    """Job appelé par APScheduler : lance le script de scraping avec garde de concurrence."""
    # If already running, skip scheduling to avoid overlap
    if _is_running or _scrape_lock.locked():
        logging.getLogger(__name__).info("Un job de scraping est déjà en cours, on l'ignore.")
        return False
    # Run synchronously in this thread when called by scheduler
    return _run_scrape_with_guard()

@app.route('/')
def index():
    state = "en cours" if _is_running or _scrape_lock.locked() else "idle"
    return f"APScheduler est en cours d'exécution. État du scraping: {state}."

@app.route('/scrape', methods=['GET'])
def trigger_scrape():
    """Déclenche le scraping si aucun job n'est en cours; sinon informe l'utilisateur que le job tourne déjà."""
    launched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Si déjà en cours, ne pas lancer un autre job
    if _is_running or _scrape_lock.locked():
        html = f"""
        <!doctype html>
        <html lang=\"fr\">
        <head>
          <meta charset=\"utf-8\">
          <title>Scraping déjà en cours</title>
          <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 2rem; color: #222; }}
            .card {{ max-width: 640px; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
            h1 {{ font-size: 1.25rem; margin: 0 0 0.5rem; }}
            .warn {{ color: #d97706; font-weight: 600; }}
            .meta {{ color: #6b7280; font-size: 0.95rem; margin-top: 0.25rem; }}
            .links {{ margin-top: 1rem; }}
            a {{ color: #2563eb; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
          </style>
        </head>
        <body>
          <div class=\"card\">
            <h1 class=\"warn\">⚠️ Un scraping est déjà en cours</h1>
            <div class=\"meta\">Demande reçue: {launched_at}</div>
            <p>Votre requête n'a pas lancé de nouveau job afin d'éviter des exécutions concurrentes. Réessayez plus tard.</p>
            <div class=\"links\">
              <ul>
                <li><a href=\"/\">Accueil</a></li>
                <li><a href=\"/health\">Vérifier l'état (health)</a></li>
              </ul>
            </div>
          </div>
        </body>
        </html>
        """
        return html, 409, {"Content-Type": "text/html; charset=utf-8"}

    # Démarrer le scraping en arrière-plan pour répondre tout de suite à l'utilisateur
    threading.Thread(target=_run_scrape_with_guard, daemon=True).start()

    html = f"""
    <!doctype html>
    <html lang=\"fr\">
    <head>
      <meta charset=\"utf-8\">
      <title>Scraping déclenché</title>
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 2rem; color: #222; }}
        .card {{ max-width: 640px; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1.25rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
        h1 {{ font-size: 1.25rem; margin: 0 0 0.5rem; }}
        .ok {{ color: #16a34a; font-weight: 600; }}
        .meta {{ color: #6b7280; font-size: 0.95rem; margin-top: 0.25rem; }}
        .links {{ margin-top: 1rem; }}
        a {{ color: #2563eb; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
      </style>
    </head>
    <body>
      <div class=\"card\">
        <h1 class=\"ok\">✅ Le scraping a bien été déclenché</h1>
        <div class=\"meta\">Horodatage: {launched_at}</div>
        <p>Le processus s'exécute en arrière-plan. Vous pouvez consulter l'état de l'application via les liens ci-dessous.</p>
        <div class=\"links\">
          <ul>
            <li><a href=\"/\">Accueil</a></li>
            <li><a href=\"/health\">Vérifier l'état (health)</a></li>
          </ul>
        </div>
      </div>
    </body>
    </html>
    """
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de santé simple pour vérifier que l'appli répond."""
    return {"status": "ok", "scraping": "running" if _is_running or _scrape_lock.locked() else "idle"}, 200

if __name__ == '__main__':
    # Configuration d'APScheduler
    logging.getLogger(__name__).info(
        f"--- Démarrage GetResults Scraper v{APP_VERSION} ---"
    )
    logging.getLogger(__name__).info("Scheduler configuré pour 'cron' à 00:00.")
    scheduler = BackgroundScheduler()
    # Planifie l'exécution de 'scraping_job' tous les jours à 00:00
    scheduler.add_job(scraping_job, 'cron', hour=0, minute=0, id='daily_scraping')
    scheduler.start()

    # Arrêt propre du scheduler quand l'appli s'arrête
    atexit.register(lambda: scheduler.shutdown())

    # Lancement de l'appli Flask (sur port 5000 par défaut)
    app.run(host='0.0.0.0', port=5001, debug=True)
