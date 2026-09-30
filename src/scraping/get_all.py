import logging
import re
from typing import List, Dict, Tuple, Optional

from src.models.models import MatchIngest, RankingIngest
from src.saving.api_client import IngestClient
from src.scraping.get_match_results import get_matches_from_url
from src.utils.metrics import timed_operation, log_summary, reset_metrics


logger = logging.getLogger(__name__)

ingest_client = IngestClient()


def _extract_poule_id(url: str) -> Optional[str]:
    match = re.search(r"poule-(\d+)", url)
    return match.group(1) if match else None


def _ingest_matches(all_match_data: List[Dict], category: str, url_start: str) -> None:
    """Ingère les matchs vers le backend."""
    pige_id = _extract_poule_id(url_start)
    effective_pool_id = pige_id if pige_id else f"UNKNOWN_{category}"

    if all_match_data:
        ingest_batch = []
        for m in all_match_data:
            model = _map_to_ingest_model(m, category, effective_pool_id)
            if model:
                ingest_batch.append(model)

        if ingest_batch:
            success = ingest_client.send_matches(ingest_batch)
            if success:
                logger.info(f"💾 {len(ingest_batch)} Matchs envoyés au Backend.")
            else:
                logger.error("❌ Echec de l'envoi des matchs au Backend.")
    else:
        logger.warning(f"⚠️ Aucun match trouvé pour '{category}'")


def _ingest_rankings(
    ranking_data: List[Dict],
    category: str,
    url_start: str,
    official_phase_name: Optional[str] = None,
) -> None:
    """Ingère les classements vers le backend."""
    pige_id = _extract_poule_id(url_start)
    effective_pool_id = pige_id if pige_id else f"UNKNOWN_{category}"

    if ranking_data:
        ranking_batch = []
        for r in ranking_data:
            model = _map_to_ranking_model(r, category, effective_pool_id, official_phase_name)
            if model:
                ranking_batch.append(model)

        if ranking_batch:
            success = ingest_client.send_rankings(ranking_batch)
            if success:
                logger.info(f"🏆 {len(ranking_batch)} Classements envoyés au Backend.")
            else:
                logger.error("❌ Echec de l'envoi des classements au Backend.")
    else:
        # Normal en début de saison : la FFHB renvoie un classement vide tant qu'aucun match n'est joué
        logger.info(f"ℹ️ Aucun classement disponible pour '{category}'")


def _map_to_ingest_model(raw_match: Dict, category: str, pool_id: str) -> Optional[MatchIngest]:
    """Transforme le dictionnaire brut du scraper en Modèle Pydantic Strict."""
    try:
        return MatchIngest(
            match_date=raw_match["match_date"],
            team_1_name=raw_match.get("team_1_name", ""),
            team_1_score=raw_match.get("team_1_score"),
            team_2_name=raw_match.get("team_2_name", ""),
            team_2_score=raw_match.get("team_2_score"),
            category=category,
            pool_id=pool_id,
            official_phase_name=raw_match.get("official_phase_name"),
            round=str(raw_match.get("journee")) if raw_match.get("journee") else None,
        )
    except Exception as e:
        logger.warning(f"⚠️ Donnée invalide ignorée : {e} | Data: {raw_match}")
        return None


def _map_to_ranking_model(
    raw_ranking: Dict,
    category: str,
    pool_id: str,
    official_phase_name: Optional[str] = None,
) -> Optional[RankingIngest]:
    """Transforme le dictionnaire brut du classement en Modèle Pydantic."""
    try:
        return RankingIngest(
            pool_id=pool_id,
            category=category,
            team_name=raw_ranking.get("team_name", ""),
            rank_number=raw_ranking.get("rank", 0),
            points=raw_ranking.get("points", 0),
            matches_played=raw_ranking.get("matches_played", 0),
            won=raw_ranking.get("won", 0),
            draws=raw_ranking.get("draws", 0),
            lost=raw_ranking.get("lost", 0),
            goal_diff=raw_ranking.get("goal_diff", 0),
            official_phase_name=official_phase_name or raw_ranking.get("official_phase_name"),
        )
    except Exception as e:
        logger.warning(f"⚠️ Classement invalide ignoré : {e} | Data: {raw_ranking}")
        return None


def get_all(url_start: str, category: str):
    reset_metrics()
    logger.info(f"🚀 [Start] Scraping '{category}' via {url_start}")

    all_match_data = []
    ranking_data = []
    official_phase_name = None

    with timed_operation("scrape_category", category=category):
        # 1. Scraping Page Initiale (matchs + classement)
        initial_matches, journees_meta, initial_ranking = _fetch_initial_page(url_start, category)
        all_match_data.extend(initial_matches)

        if initial_matches and initial_matches[0].get("official_phase_name"):
            official_phase_name = initial_matches[0]["official_phase_name"]

        if initial_ranking:
            ranking_data = initial_ranking

        # 2. Scraping Pagination
        urls_to_visit = _build_pagination_urls(url_start, journees_meta)
        paginated_matches, paginated_ranking = _fetch_paginated_pages(urls_to_visit, category)
        all_match_data.extend(paginated_matches)

        if not ranking_data and paginated_ranking:
            ranking_data = paginated_ranking

        # 3. Transformation et Envoi via API
        with timed_operation("ingest_rankings", category=category, count=len(ranking_data)):
            _ingest_rankings(ranking_data, category, url_start, official_phase_name)

        with timed_operation("ingest_matches", category=category, count=len(all_match_data)):
            _ingest_matches(all_match_data, category, url_start)

    log_summary()
    logger.info(f"🏁 [End] Scraping terminé pour '{category}'")


def _fetch_initial_page(url: str, category: str) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Récupère matchs, métadonnées et classement de la première page."""
    matches, meta, ranking = get_matches_from_url(url, category)
    return matches, meta, ranking


def _build_pagination_urls(url_start: str, journees_meta: List[Dict]) -> List[str]:
    """Construit les URLs de pagination."""
    if not journees_meta:
        return []

    base_url_pattern = re.sub(r"journee-\d+/?", "journee-{}/", url_start)
    if base_url_pattern == url_start:
        if not base_url_pattern.endswith("/"):
            base_url_pattern += "/"
        base_url_pattern += "journee-{}/"

    target_urls = []
    for journee in journees_meta:
        num = journee.get("journeeNumero") or journee.get("journee_numero") or journee.get("numero")

        if not num or f"journee-{num}" in url_start:
            continue

        target_urls.append(base_url_pattern.format(num))

    return target_urls


def _fetch_paginated_pages(urls: List[str], category: str) -> Tuple[List[Dict], List[Dict]]:
    """Scrape les pages suivantes."""
    results = []
    found_ranking = []

    for url in urls:
        page_matches, _, page_ranking = get_matches_from_url(url, category)

        if page_matches:
            results.extend(page_matches)

        if page_ranking and not found_ranking:
            found_ranking = page_ranking

    return results, found_ranking
