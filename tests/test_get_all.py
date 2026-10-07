from unittest.mock import patch

from src.scraping.get_all import (
    _extract_poule_id,
    _map_to_ingest_model,
    _map_to_ranking_model,
    _build_pagination_urls,
    get_all,
)
from src.models.models import MatchIngest, RankingIngest


class TestExtractPouleId:
    """Tests pour l'extraction de l'ID de poules depuis l'URL."""

    def test_extract_poule_id_with_poule(self):
        url = "https://www.ffhandball.fr/competitions/saison-2025-2026/regional/18-ans-f/poule-123456/"
        assert _extract_poule_id(url) == "123456"

    def test_extract_poule_id_without_poule(self):
        url = "https://www.ffhandball.fr/competitions/saison-2025-2026/regional/18-ans-f/"
        assert _extract_poule_id(url) is None

    def test_extract_poule_id_with_multiple_matches(self):
        url = "https://www.ffhandball.fr/competitions/saison-2025-2026/regional/18-ans-f/poule-987654/"
        assert _extract_poule_id(url) == "987654"

    def test_extract_poule_id_empty_string(self):
        assert _extract_poule_id("") is None


class TestMapToIngestModel:
    """Tests pour la transformation des données de match brut en modèle Pydantic."""

    def test_map_valid_match(self):
        raw_match = {
            "match_date": "2025-01-15 14:30:00",
            "team_1_name": "Club A",
            "team_1_score": 25,
            "team_2_name": "Club B",
            "team_2_score": 22,
            "competition": "-18M",
            "journee": "1",
            "official_phase_name": "Excellence",
        }
        result = _map_to_ingest_model(raw_match, "-18M", "123456")

        assert result is not None
        assert isinstance(result, MatchIngest)
        assert result.team_1_name == "Club A"
        assert result.team_2_name == "Club B"
        assert result.team_1_score == 25
        assert result.category == "-18M"
        assert result.pool_id == "123456"
        assert result.round == "1"
        assert result.official_phase_name == "Excellence"

    def test_map_match_with_missing_optional_fields(self):
        raw_match = {
            "match_date": "2025-01-15 14:30:00",
            "team_1_name": "Club A",
            "team_1_score": None,
            "team_2_name": "Club B",
            "team_2_score": None,
        }
        result = _map_to_ingest_model(raw_match, "-18M", "123456")

        assert result is not None
        assert result.team_1_score is None
        assert result.team_2_score is None
        assert result.round is None
        assert result.official_phase_name is None

    def test_map_match_unknown_team_uses_name_directly(self):
        """Les noms d'équipes sont utilisés directement, pas de résolution par ID."""
        raw_match = {
            "match_date": "2025-01-15 14:30:00",
            "team_1_name": "Équipe Inconnue",
            "team_2_name": "Club B",
        }
        result = _map_to_ingest_model(raw_match, "-18M", "123456")

        assert result is not None
        assert result.team_1_name == "Équipe Inconnue"
        assert result.team_2_name == "Club B"

    def test_map_match_with_invalid_date(self):
        raw_match = {"match_date": "invalid-date", "team_1_name": "Club A", "team_2_name": "Club B"}
        result = _map_to_ingest_model(raw_match, "-18M", "123456")

        assert result is None

    def test_map_match_with_missing_required_field(self):
        raw_match = {
            "team_1_name": "Club A"
            # match_date manquant
        }
        result = _map_to_ingest_model(raw_match, "-18M", "123456")

        assert result is None


class TestMapToRankingModel:
    """Tests pour la transformation des données de classement brut en modèle Pydantic."""

    def test_map_valid_ranking(self):
        raw_ranking = {
            "team_name": "Team A",
            "rank": 1,
            "points": 25,
            "matches_played": 10,
            "won": 8,
            "draws": 1,
            "lost": 1,
            "goal_diff": 50,
        }
        result = _map_to_ranking_model(raw_ranking, "-18M", "123456")

        assert result is not None
        assert isinstance(result, RankingIngest)
        assert result.team_name == "Team A"
        assert result.rank_number == 1
        assert result.points == 25
        assert result.category == "-18M"
        assert result.pool_id == "123456"

    def test_map_ranking_with_missing_optional_fields(self):
        raw_ranking = {"team_name": "Team B"}
        result = _map_to_ranking_model(raw_ranking, "-18M", "123456")

        assert result is not None
        assert result.rank_number == 0
        assert result.points == 0
        assert result.matches_played == 0

    def test_map_ranking_with_official_phase_name(self):
        raw_ranking = {"team_name": "Team A", "rank": 1, "official_phase_name": "Division 1"}
        result = _map_to_ranking_model(raw_ranking, "-18M", "123456", "Excellence")

        assert result is not None
        assert result.official_phase_name == "Excellence"

    def test_map_ranking_unknown_team_uses_name_directly(self):
        """Le nom d'équipe est utilisé directement."""
        raw_ranking = {
            "team_name": "Équipe Inconnue",
            "rank": 1,
        }
        result = _map_to_ranking_model(raw_ranking, "-18M", "123456")

        assert result is not None
        assert result.team_name == "Équipe Inconnue"

    def test_map_ranking_with_missing_team_name(self):
        raw_ranking = {
            "rank": 1
            # team_name manquant → chaîne vide
        }
        result = _map_to_ranking_model(raw_ranking, "-18M", "123456")

        assert result is not None
        assert result.team_name == ""


class TestBuildPaginationUrls:
    """Tests pour la construction des URLs de pagination."""

    def test_build_urls_from_meta(self):
        url_start = "https://www.ffhandball.fr/competitions/poule-123/journee-1/"
        journees_meta = [{"journeeNumero": "2"}, {"journeeNumero": "3"}, {"journeeNumero": "4"}]
        urls = _build_pagination_urls(url_start, journees_meta)

        assert len(urls) == 3
        assert "journee-2" in urls[0]
        assert "journee-3" in urls[1]
        assert "journee-4" in urls[2]

    def test_build_urls_empty_meta(self):
        url_start = "https://www.ffhandball.fr/competitions/poule-123/journee-1/"
        urls = _build_pagination_urls(url_start, [])

        assert urls == []

    def test_build_urls_with_alternative_keys(self):
        url_start = "https://www.ffhandball.fr/competitions/poule-123/journee-1/"
        journees_meta = [{"journee_numero": "2"}, {"numero": "3"}]
        urls = _build_pagination_urls(url_start, journees_meta)

        assert len(urls) == 2

    def test_build_urls_skips_current_page(self):
        url_start = "https://www.ffhandball.fr/competitions/poule-123/journee-1/"
        journees_meta = [{"journeeNumero": "1"}, {"journeeNumero": "2"}]
        urls = _build_pagination_urls(url_start, journees_meta)

        assert len(urls) == 1
        assert "journee-2" in urls[0]


class TestGetAll:
    """Tests pour la fonction principale get_all."""

    @patch("src.scraping.get_all._fetch_initial_page")
    @patch("src.scraping.get_all._build_pagination_urls")
    @patch("src.scraping.get_all._fetch_paginated_pages")
    @patch("src.scraping.get_all.ingest_client")
    def test_get_all_success(
        self, mock_ingest_client, mock_fetch_paginated, mock_build_urls, mock_fetch_initial
    ):
        mock_fetch_initial.return_value = (
            [
                {
                    "match_date": "2025-01-15 14:30:00",
                    "team_1_name": "A",
                    "team_1_score": 25,
                    "team_2_name": "B",
                    "team_2_score": 20,
                }
            ],
            [{"journeeNumero": "2"}],
            [{"team_name": "Team A", "rank": 1}],
        )
        mock_build_urls.return_value = ["url2"]
        mock_fetch_paginated.return_value = (
            [
                {
                    "match_date": "2025-01-22 14:30:00",
                    "team_1_name": "C",
                    "team_1_score": 30,
                    "team_2_name": "D",
                    "team_2_score": 25,
                }
            ],
            [],
        )
        mock_ingest_client.send_matches.return_value = True
        mock_ingest_client.send_rankings.return_value = True

        get_all("http://test.com/poule-123/journee-1/", "-18M")

        assert mock_ingest_client.send_matches.call_count == 1
        assert mock_ingest_client.send_rankings.call_count == 1

    @patch("src.scraping.get_all._fetch_initial_page")
    @patch("src.scraping.get_all._build_pagination_urls")
    @patch("src.scraping.get_all._fetch_paginated_pages")
    @patch("src.scraping.get_all.ingest_client")
    def test_get_all_no_matches(
        self, mock_ingest_client, mock_fetch_paginated, mock_build_urls, mock_fetch_initial
    ):
        mock_fetch_initial.return_value = ([], [], [])
        mock_build_urls.return_value = []
        mock_fetch_paginated.return_value = ([], [])

        get_all("http://test.com/poule-123/journee-1/", "-18M")

        mock_ingest_client.send_matches.assert_not_called()
        mock_ingest_client.send_rankings.assert_not_called()

    @patch("src.scraping.get_all._fetch_initial_page")
    @patch("src.scraping.get_all._build_pagination_urls")
    @patch("src.scraping.get_all._fetch_paginated_pages")
    @patch("src.scraping.get_all.ingest_client")
    def test_get_all_partial_failure(
        self, mock_ingest_client, mock_fetch_paginated, mock_build_urls, mock_fetch_initial
    ):
        mock_fetch_initial.return_value = (
            [
                {
                    "match_date": "2025-01-15 14:30:00",
                    "team_1_name": "A",
                    "team_1_score": 25,
                    "team_2_name": "B",
                    "team_2_score": 20,
                }
            ],
            [],
            [{"team_name": "Team A", "rank": 1}],
        )
        mock_build_urls.return_value = []
        mock_fetch_paginated.return_value = ([], [])
        mock_ingest_client.send_matches.return_value = False
        mock_ingest_client.send_rankings.return_value = True

        get_all("http://test.com/poule-123/journee-1/", "-18M")

        assert mock_ingest_client.send_matches.call_count == 1
        assert mock_ingest_client.send_rankings.call_count == 1


class TestMapFfhbIds:
    """Les identifiants FFHB (AEK-56) arrivent jusqu'au payload d'ingestion."""

    def test_match_ids_are_mapped(self):
        raw_match = {
            "match_date": "2025-10-04 21:00:00",
            "match_id": "2390866",
            "team_1_id": "1240516",
            "team_1_name": "ALES CEVENNES HB",
            "team_2_id": "1240523",
            "team_2_name": "LUNEL MARSILLARGUES HBC",
        }
        result = _map_to_ingest_model(raw_match, "SG", "169284")
        dumped = result.model_dump(mode="json")
        assert dumped["match_id"] == "2390866"
        assert dumped["team_1_id"] == "1240516"
        assert dumped["team_2_id"] == "1240523"

    def test_match_without_ids_still_valid(self):
        raw_match = {"match_date": "2025-10-04 21:00:00", "team_1_name": "A", "team_2_name": "B"}
        result = _map_to_ingest_model(raw_match, "SG", "169284")
        assert result is not None
        assert result.match_id is None

    def test_ranking_team_id_is_mapped(self):
        result = _map_to_ranking_model({"team_name": "LUNEL MARSILLARGUES HBC", "team_id": "1240523"}, "SG", "169284")
        assert result.model_dump(mode="json")["team_id"] == "1240523"
