import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional

from src.saving.db_logger import create_log_entry, update_log_entry
from src.utils.logging_config import configure_logging
from src.scraping.get_all import get_all
from src.utils.sources.api_fetcher import get_urls_from_api
from src.utils.rate_limiter import RateLimiter
from src.settings import get_scraper_settings, get_backend_settings, get_source_api_settings, get_db_settings
from src.version import build_identity


@dataclass
class ScrapingResult:
    """Résultat du scraping d'une source."""
    source_id: str
    category: str
    success: bool
    error: Optional[str] = None


def _scrape_single_source(entry: dict, logger: logging.Logger) -> ScrapingResult:
    """
    Scrape une source individuelle. Fonction exécutée par chaque worker.
    """
    source_id = entry.get("id", "unknown")
    target_url = entry.get("url")
    category_label = entry.get("category", "Inconnue")

    if not source_id or not target_url:
        return ScrapingResult(
            source_id=str(source_id),
            category=category_label,
            success=False,
            error="ID ou URL manquant"
        )

    try:
        get_all(target_url, category_label)
        return ScrapingResult(
            source_id=str(source_id),
            category=category_label,
            success=True
        )
    except Exception as e:
        logger.exception(f"❌ Erreur sur source ID {source_id} ({category_label}): {e}")
        return ScrapingResult(
            source_id=str(source_id),
            category=category_label,
            success=False,
            error=str(e)
        )


def run_daily_scraping(max_workers: int = None, rate_limit_delay: float = None, skip_config_check: bool = False):
    """
    Exécute le scraping quotidien avec parallélisation.

    Args:
        max_workers: Nombre de workers parallèles (défaut: depuis settings)
        rate_limit_delay: Délai minimum entre requêtes en secondes (défaut: depuis settings)
    """
    configure_logging()
    logger = logging.getLogger(__name__)
    if not skip_config_check:
        check_configuration()

    # Configuration depuis settings (validées par Pydantic)
    scraper_settings = get_scraper_settings()
    if max_workers is None:
        max_workers = scraper_settings.max_workers
    if rate_limit_delay is None:
        rate_limit_delay = scraper_settings.rate_limit_delay

    # Initialiser le rate limiter global
    RateLimiter(min_delay=rate_limit_delay, burst_limit=10, burst_window=15.0)

    log_id = create_log_entry()
    start_time = time.time()
    logger.info(
        f"🚀 Job scraping: début — scraper {build_identity()} "
        f"(workers={max_workers}, rate_limit={rate_limit_delay}s)"
    )

    job_status = "SUCCESS"
    errors: List[str] = []
    success_count = 0
    total_count = 0

    try:
        urls_list = get_urls_from_api()
        total_count = len(urls_list)

        if not urls_list:
            logger.warning("⚠️ Aucune source à scraper.")
            return

        logger.info(f"📋 {total_count} sources à traiter")

        # Exécution parallèle avec ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Soumettre toutes les tâches
            future_to_entry = {
                executor.submit(_scrape_single_source, entry, logger): entry
                for entry in urls_list
            }

            # Collecter les résultats au fur et à mesure
            for future in as_completed(future_to_entry):
                result = future.result()

                if result.success:
                    success_count += 1
                    logger.info(f"✅ [{success_count}/{total_count}] {result.category} terminé")
                else:
                    errors.append(f"{result.category} (ID {result.source_id}): {result.error}")

        # Déterminer le statut final
        if errors:
            if success_count == 0:
                job_status = "FAILURE"
            else:
                job_status = "PARTIAL_SUCCESS"

    except Exception as e:
        logger.exception(f"🔥 Erreur fatale globale: {e}")
        job_status = "FAILURE"
        errors.append(f"Erreur fatale: {str(e)}")

    finally:
        elapsed_time = time.time() - start_time
        error_message = "; ".join(errors) if errors else None

        logger.info(f"🏁 Job terminé en {elapsed_time:.2f}s. "
                    f"Succès: {success_count}/{total_count}. Statut: {job_status}")

        update_log_entry(
            log_id=log_id,
            status=job_status,
            duration=elapsed_time,
            message=error_message
        )


def check_configuration():
    """Vérifie que toutes les variables d'environnement critiques sont configurées."""
    logger = logging.getLogger(__name__)

    backend_settings = get_backend_settings()
    source_settings = get_source_api_settings()
    db_settings = get_db_settings()

    log_settings_keys(backend_settings, "BackendAPISettings", logger)
    log_settings_keys(source_settings, "SourceAPISettings", logger)
    log_settings_keys(db_settings, "DatabaseSettings", logger)

    errors = []

    # Vérification des URLs
    if not backend_settings.api_url:
        errors.append("❌ BACKEND_API_URL est manquant")
    if not backend_settings.api_key:
        errors.append("❌ BACKEND_API_KEY est manquant")
    if not source_settings.api_url:
        errors.append("❌ API_URL est manquant")
    if not source_settings.api_key:
        errors.append("❌ API_KEY est manquant")
    if not db_settings.is_configured:
        errors.append("❌ Configuration MySQL incomplète (MYSQL_USER/PASSWORD/DATABASE)")

    # Test de connexion au backend
    if backend_settings.api_url:
        import requests
        from urllib.parse import urlsplit

        parts = urlsplit(backend_settings.api_url)
        backend_base = f"{parts.scheme}://{parts.netloc}"
        try:
            response = requests.get(f"{backend_base}/api/test", timeout=5)
            logger.info(f"✅ Backend accessible (status {response.status_code})")

            # /api/test est public : on valide la clé sur une route protégée
            auth_response = requests.get(
                f"{backend_base}/api/competitions",
                headers={"X-API-KEY": backend_settings.api_key},
                timeout=5
            )
            if auth_response.status_code in (401, 403):
                errors.append(
                    f"❌ BACKEND_API_KEY refusée par le backend ({auth_response.status_code}) : "
                    "elle doit être identique à APP_API_KEY côté backend"
                )
            else:
                logger.info(f"✅ BACKEND_API_KEY acceptée (status {auth_response.status_code})")
        except Exception as e:
            errors.append(f"❌ Backend inaccessible : {e}")

    if errors:
        for error in errors:
            logger.error(error)
        raise RuntimeError("Configuration invalide, arrêt du scraper.")

    logger.info("✅ Configuration validée, démarrage du scraping...")

def log_settings_keys(settings_instance, label: str, logger: logging.Logger):
    prefix = settings_instance.model_config.get("env_prefix", "")
    alias_map = {
        field_name: (field_info.validation_alias or f"{prefix}{field_name}").upper()
        for field_name, field_info in settings_instance.model_fields.items()
    }
    logger.info(f"📋 {label} lit les variables :")
    for field_name, env_key in alias_map.items():
        present = env_key in os.environ
        logger.info(f"   - {env_key} → {'✅ présent' if present else '❌ absent'}")


if __name__ == "__main__":
    run_daily_scraping()