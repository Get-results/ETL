import hashlib
import logging
import json
import html
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple, Optional

from src.config import DEBUG_DIR
from src.scraping.get_ranking_api import get_ranking_from_api
from src.settings import get_scraper_settings
from src.utils.format_date import format_date
from src.utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def _save_debug_html(url: str, content: str, prefix: str = ""):
    """
    Sauvegarde le HTML brut dans le dossier debug pour analyse.
    Génère un nom de fichier unique basé sur l'URL et le timestamp.
    """
    try:
        # Création d'un hash court de l'URL pour éviter les caractères interdits dans les noms de fichiers
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Nettoyage du préfixe
        safe_prefix = "".join([c for c in prefix if c.isalnum() or c in ('-', '_')]).strip()
        filename = f"{timestamp}_{safe_prefix}_{url_hash}.html"

        filepath = os.path.join(DEBUG_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"💾 HTML brut sauvegardé : {filename}")

    except Exception as e:
        logger.warning(f"⚠️ Impossible de sauvegarder le HTML de debug : {e}")


def fetch_html(url: str, save_debug: bool = False, debug_prefix: str = "dump") -> Optional[str]:
    """
    Récupère le HTML brut via requests avec rate limiting.
    Args:
        url: L'URL cible.
        save_debug: Si True, sauvegarde le fichier localement.
        debug_prefix: Préfixe pour le nom du fichier de debug.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        # Rate limiting avant la requête
        limiter = get_rate_limiter()
        limiter.wait()

        timeout = get_scraper_settings().request_timeout
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        html_text = response.text

        # HOOK DE DEBUG
        if save_debug:
            _save_debug_html(url, html_text, debug_prefix)

        return html_text

    except Exception as e:
        logger.error(f"Erreur réseau sur {url} : {e}")
        return None


def get_matches_from_url(url: str, category: str) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Orchestrateur principal du scraping pour une poule donnée.

    Stratégie Hybride "Multi-Sources" :
    1. Calcule l'URL 'Classements' à partir de l'URL 'Matchs'.
    2. Appelle l'API sécurisée pour récupérer le Classement ET le Titre Officiel (Méta-donnée).
    3. Scrape la page HTML actuelle pour récupérer les Matchs et la Pagination.
    4. Injecte le Titre Officiel (official_phase_name) dans tous les objets (Matchs et Classement)
       pour permettre la distinction des onglets dans l'application.

    Args:
        url (str): L'URL de la page des rencontres (source primaire).
        category (str): Le code catégorie générique (ex: "SF", "M15").

    Returns:
        Tuple: (Liste des Matchs enrichis, Liste des Journées, Liste du Classement enrichi).
    """
    # 1. Récupération HTML (Matchs)
    html_content = fetch_html(url)
    if not html_content:
        return [], [], []

    soup = BeautifulSoup(html_content, "html.parser")

    # 2. Récupération API (Classement + Titre Officiel)
    # Transformation d'URL : ".../journee-X/" -> ".../classements/"
    base_url = url.split("journee-")[0] if "journee-" in url else url.replace("/rencontres", "")
    if base_url.endswith("/"):
        ranking_url = f"{base_url}classements/"
    else:
        ranking_url = f"{base_url}/classements/"

    official_phase_name, ranking = get_ranking_from_api(ranking_url)

    if official_phase_name:
        logger.info(f"✨ Phase identifiée : '{official_phase_name}' (pour {category})")
        # Injection du nom officiel dans les objets classement
        for row in ranking:
            row['official_phase_name'] = official_phase_name
    else:
        logger.warning(f"⚠️ Titre officiel non trouvé pour {url}, fallback sur category.")

    # 3. Extraction des Matchs (avec injection du titre)
    current_journee = _extract_journee_from_url(url)
    matches = _extract_matches_from_soup(soup, category, current_journee, official_phase_name)

    # 4. Extraction de la Pagination
    journees_meta = _extract_pagination_meta(soup, category)

    return matches, journees_meta, ranking

def _extract_journee_from_url(url: str) -> Optional[str]:
    """Extrait le numéro de journée (ex: '1') depuis l'URL."""
    match = re.search(r"journee-(\d+)", url)
    return match.group(1) if match else None


def _extract_matches_from_soup(soup: BeautifulSoup, category: str, default_journee: Optional[str], official_phase_name: Optional[str] = None) -> List[Dict]:
    """
    Extrait la liste brute des rencontres depuis le composant React et délègue le parsing.
    Passe le 'official_phase_name' au processeur unitaire.
    """
    component = soup.find("smartfire-component", attrs={"name": "competitions---rencontre-list"})

    if not component:
        return []

    results = []
    try:
        raw_attr = component.get("attributes", "{}")
        json_data = json.loads(html.unescape(raw_attr))
        rencontres = json_data.get("rencontres", [])

        logger.info(f"📊 Traitement de {len(rencontres)} matchs pour {category} (J{default_journee})")

        for match_json in rencontres:
            processed_match = _process_single_match(match_json, category, default_journee, official_phase_name)
            if processed_match:
                results.append(processed_match)

    except Exception as e:
        logger.error(f"Erreur parsing JSON rencontres pour {category}: {e}")

    return results


def _process_single_match(match: Dict, category: str, default_journee: Optional[str],
                          official_phase_name: Optional[str] = None) -> Optional[Dict]:
    """
    Transforme un objet match JSON brut en dictionnaire normalisé pour la BDD.

    Enrichissement :
    - Ajoute le champ 'official_phase_name' (ex: "Excellence") pour différencier les phases
      au sein d'une même catégorie (ex: "SF").
    """
    raw_date = match.get("date")
    formatted_date = None

    if raw_date:
        dt_obj = format_date(raw_date)
        if dt_obj:
            formatted_date = dt_obj.strftime("%Y-%m-%d %H:%M:%S")

    if not formatted_date:
        teams = f"{match.get('equipe1Libelle')} vs {match.get('equipe2Libelle')}"
        if raw_date:
            logger.warning(f"⚠️ Date invalide pour match: {teams} ('{raw_date}')")
        else:
            # Cas normal : la FFHB ne publie pas encore la date des journées futures
            logger.debug(f"📅 Date non encore programmée, match ignoré: {teams}")
        return None

    # Helper pour convertir les scores en int
    def parse_score(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    return {
        "match_date": formatted_date,
        "team_1_name": match.get("equipe1Libelle", "Nom non disponible"),
        "team_1_score": parse_score(match.get("equipe1Score")),
        "team_2_name": match.get("equipe2Libelle", "Nom non disponible"),
        "team_2_score": parse_score(match.get("equipe2Score")),
        "match_link": None,
        "competition": category,
        "journee": match.get("journeeNumero", default_journee),
        # NOUVEAU CHAMP CRITIQUE
        "official_phase_name": official_phase_name
    }

def _extract_pagination_meta(soup: BeautifulSoup, category: str) -> List[Dict]:
    """Gère la logique complexe de récupération de la liste des journées."""
    # Il y a deux noms de composants possibles selon les pages
    selector = soup.find("smartfire-component", attrs={"name": "competitions---poule-selector"})
    if not selector:
        selector = soup.find("smartfire-component", attrs={"name": "competitions---journee-selector"})

    if not selector:
        return []

    try:
        raw_attr = selector.get("attributes", "{}")
        main_json = json.loads(html.unescape(raw_attr))

        # Stratégie en entonnoir pour trouver 'journees'
        raw_journees = (
                main_json.get("journees") or
                (main_json.get("poule") or {}).get("journees") or
                (main_json.get("selected_poule") or {}).get("journees")
        )

        if isinstance(raw_journees, str):
            return json.loads(raw_journees)
        elif isinstance(raw_journees, list):
            return raw_journees

    except Exception as e:
        logger.warning(f"Impossible d'extraire la liste des journées pour {category}: {e}")

    return []