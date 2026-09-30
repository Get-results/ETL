import logging
import random
import time
import requests
from typing import List

from src.models.models import MatchIngest, RankingIngest
from src.settings import get_backend_settings, get_scraper_settings

logger = logging.getLogger(__name__)


class IngestClient:
    """Client HTTP pour l'ingestion des données vers le backend."""

    NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        """
        Args:
            max_retries: Nombre maximum de tentatives (défaut: 3)
            base_delay: Délai initial en secondes pour le backoff exponentiel (défaut: 1.0)
        """
        backend_settings = get_backend_settings()
        scraper_settings = get_scraper_settings()

        self.api_url = backend_settings.api_url
        self.rankings_api_url = backend_settings.effective_rankings_url
        self.api_key = backend_settings.api_key
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = scraper_settings.request_timeout

        logger.info(
            f"🔧 Config backend: api_url={self.api_url}, api_key={'***' if self.api_key else None}"
        )

        if not self.api_key:
            logger.warning(
                "⚠️ Aucune API KEY définie (BACKEND_API_KEY). Les requêtes risquent d'échouer (401/403)."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "GetResults-Scraper/1.0",
            }
        )

    def _send_batch(self, url: str, payload: list, item_type: str) -> bool:
        """
        Envoie un batch de données au backend avec retry et backoff exponentiel.

        Args:
            url: URL de l'endpoint
            payload: Liste de dictionnaires à envoyer
            item_type: Type d'élément pour les logs ("matchs" ou "classements")

        Returns:
            True si succès, False sinon.
        """
        last_exception = None
        last_response = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"📤 Envoi de {len(payload)} {item_type} vers {url} (tentative {attempt}/{self.max_retries})..."
                )
                response = self.session.post(url, json=payload, timeout=self.timeout)

                if response.status_code in (200, 201, 204):
                    logger.info(f"✅ Ingestion {item_type} réussie.")
                    return True

                last_response = response

                if response.status_code in self.NON_RETRYABLE_STATUS_CODES:
                    if response.status_code == 401:
                        logger.error(
                            "🔑 Non authentifié (401). BACKEND_API_KEY ne correspond pas à APP_API_KEY du backend."
                        )
                    elif response.status_code == 403:
                        logger.error("⛔ Accès refusé (403). Vérifiez BACKEND_API_KEY.")
                    else:
                        logger.error(f"❌ Erreur Backend ({response.status_code}): {response.text}")
                    return False

                logger.warning(f"⚠️ Erreur serveur ({response.status_code}), retry possible...")

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"⚠️ Erreur réseau : {e}")

            if attempt < self.max_retries:
                delay = self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.info(f"⏳ Attente de {delay:.1f}s avant retry...")
                time.sleep(delay)

        if last_exception:
            logger.error(
                f"🔥 Échec définitif après {self.max_retries} tentatives. Dernière erreur : {last_exception}"
            )
        elif last_response:
            logger.error(
                f"🔥 Échec définitif après {self.max_retries} tentatives. Dernier status : {last_response.status_code}"
            )

        return False

    def send_matches(self, matches: List[MatchIngest]) -> bool:
        """
        Envoie un batch de matchs au backend.
        Retourne True si succès, False sinon.
        """
        if not matches:
            return True

        payload = [m.model_dump(mode="json") for m in matches]
        return self._send_batch(self.api_url, payload, "matchs")

    def send_rankings(self, rankings: List[RankingIngest]) -> bool:
        """
        Envoie un batch de classements au backend.
        Retourne True si succès, False sinon.
        """
        if not rankings:
            return True

        if not self.rankings_api_url:
            logger.warning(
                "⚠️ Aucune URL de rankings configurée (BACKEND_RANKINGS_API_URL). Envoi ignoré."
            )
            return False

        payload = [r.model_dump(mode="json") for r in rankings]
        return self._send_batch(self.rankings_api_url, payload, "classements")
