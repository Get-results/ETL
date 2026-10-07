import json
import html
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_ffhb_id(value) -> Optional[str]:
    """Normalise un identifiant FFHB (equipeId, ext_rencontreId...) en str ; None si absent ou vide."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def parse_ranking_list(ranking_list: List[Dict]) -> List[Dict]:
    """
    Fonction PARTAGÉE : Parse une liste brute (API ou HTML) en format standardisé.
    Gère les différences de clés (anglais/français) et les types.
    """
    parsed_ranking = []
    for row in ranking_list:
        # 1. Extraction du nom (plusieurs variantes possibles)
        team_name = (
            row.get("teamName")
            or row.get("label")
            or row.get("equipeLibelle")
            or row.get("equipe_libelle")
            or row.get("team", {}).get("name")
        )

        if not team_name:
            continue

        # 2. Helper interne sécurisé
        def get_int(keys, default=0):
            if isinstance(keys, str):
                keys = [keys]
            for k in keys:
                val = row.get(k)
                if val is not None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        pass
            return default

        # 3. Construction de l'objet standardisé
        logo_filename = (
            row.get("structure_logo") or row.get("equipe_logo") or row.get("logo") or None
        )

        team_data = {
            "team_id": parse_ffhb_id(row.get("equipeId")),
            "rank": get_int(["rank", "rang", "sortOrder", "place"]),
            "team_name": team_name.strip(),
            "logo_filename": logo_filename,
            "points": get_int(["points", "pts", "point"]),
            # Calcul des matchs joués si non présent explicitement
            "matches_played": get_int(["matchesPlayed", "joues", "matchsJoues", "joue"])
            or (get_int(["won", "gagne"]) + get_int(["lost", "perdu"]) + get_int(["draws", "nul"])),
            "won": get_int(["won", "gagnes", "gagne"]),
            "draws": get_int(["draws", "nuls", "nul"]),
            "lost": get_int(["lost", "perdus", "perdu"]),
            "goal_diff": get_int(["goalDifference", "diff", "difference"]),
            "goals_for": get_int(["goalsFor", "butsPour", "butPlus"]),
            "goals_against": get_int(["goalsAgainst", "butsContre", "butMoins"]),
        }
        parsed_ranking.append(team_data)

    return parsed_ranking


def extract_ranking_from_soup(soup: BeautifulSoup) -> List[Dict]:
    """Scanner HTML (Fallback) : Cherche le classement dans les composants de la page."""
    components = soup.find_all("smartfire-component")

    for comp in components:
        raw_attrs = comp.get("attributes")
        if not raw_attrs:
            continue

        try:
            data = json.loads(html.unescape(raw_attrs))
            candidates = _find_ranking_candidates(data)

            for candidate_list in candidates:
                if _is_valid_ranking_list(candidate_list):
                    # On utilise la fonction partagée !
                    return parse_ranking_list(candidate_list)

        except json.JSONDecodeError:
            continue

    return []


def _find_ranking_candidates(data: Any) -> List[List]:
    """Cherche récursivement des listes candidates dans le JSON."""
    candidates = []
    if isinstance(data, dict):
        # Clés fréquentes
        for key in ["ranking", "rows", "classification", "standings", "classements"]:
            if key in data and isinstance(data[key], list):
                candidates.append(data[key])

        for value in data.values():
            if isinstance(value, dict):
                candidates.extend(_find_ranking_candidates(value))
            elif isinstance(value, list) and len(value) > 0:
                candidates.append(value)
    return candidates


def _is_valid_ranking_list(data_list: List) -> bool:
    """Vérifie si une liste ressemble à un classement (Duck Typing)."""
    if not data_list or not isinstance(data_list[0], dict):
        return False

    first = data_list[0]
    has_name = any(
        k in first for k in ["teamName", "label", "equipeLibelle", "team", "equipe_libelle"]
    )
    has_stats = any(k in first for k in ["points", "pts", "rank", "won"])

    return has_name and has_stats
