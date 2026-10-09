from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from src.scraping.get_match_results import (
    _extract_journee_from_url,
    _extract_matches_from_soup,
    _process_single_match,
    _extract_pagination_meta,
    get_matches_from_url,
    fetch_html,
)


class TestExtractJourneeFromUrl:
    """Tests pour l'extraction du numéro de journée depuis l'URL."""

    def test_extract_journee_with_number(self):
        url = "https://www.ffhandball.fr/competitions/poule-123/journee-5/"
        assert _extract_journee_from_url(url) == "5"

    def test_extract_journee_without_number(self):
        url = "https://www.ffhandball.fr/competitions/poule-123/classements/"
        assert _extract_journee_from_url(url) is None

    def test_extract_journee_empty_string(self):
        assert _extract_journee_from_url("") is None


class TestProcessSingleMatch:
    """Tests pour le traitement d'un match unique."""

    def test_process_valid_match(self):
        match = {
            "date": "2025-01-15T14:30:00",
            "equipe1Libelle": "Club A",
            "equipe1Score": "25",
            "equipe2Libelle": "Club B",
            "equipe2Score": "22",
            "journeeNumero": "1"
        }
        result = _process_single_match(match, "-18M", "1", "Excellence")

        assert result is not None
        assert result["team_1_name"] == "Club A"
        assert result["team_1_score"] == 25
        assert result["team_2_name"] == "Club B"
        assert result["team_2_score"] == 22
        assert result["competition"] == "-18M"
        assert result["journee"] == "1"
        assert result["official_phase_name"] == "Excellence"

    def test_match_date_is_paris_time_summer(self):
        """Heure d'été (UTC+2) : l'heure de Paris est conservée, pas convertie en UTC."""
        match = {"date": "2026-10-04T12:00:00+02:00", "equipe1Libelle": "A", "equipe2Libelle": "B"}
        assert _process_single_match(match, "-11F", "1")["match_date"] == "2026-10-04 12:00:00"

    def test_match_date_is_paris_time_winter(self):
        """Heure d'hiver (UTC+1)."""
        match = {"date": "2026-12-12T20:30:00+01:00", "equipe1Libelle": "A", "equipe2Libelle": "B"}
        assert _process_single_match(match, "-11F", "1")["match_date"] == "2026-12-12 20:30:00"

    def test_match_date_utc_input_converted_to_paris(self):
        """Une date fournie en UTC est ramenée à l'heure de Paris."""
        match = {"date": "2026-10-04T10:00:00Z", "equipe1Libelle": "A", "equipe2Libelle": "B"}
        assert _process_single_match(match, "-11F", "1")["match_date"] == "2026-10-04 12:00:00"

    def test_match_date_naive_input_kept_as_paris(self):
        """Une date sans fuseau est considérée comme heure de Paris et reste inchangée."""
        match = {"date": "2025-01-15T14:30:00", "equipe1Libelle": "A", "equipe2Libelle": "B"}
        assert _process_single_match(match, "-11F", "1")["match_date"] == "2025-01-15 14:30:00"

    def test_process_match_with_invalid_date(self):
        match = {
            "date": "invalid-date",
            "equipe1Libelle": "Club A",
            "equipe1Score": "25",
            "equipe2Libelle": "Club B",
            "equipe2Score": "22"
        }
        result = _process_single_match(match, "-18M", "1")

        assert result is None

    def test_process_match_with_missing_scores(self):
        match = {
            "date": "2025-01-15T14:30:00",
            "equipe1Libelle": "Club A",
            "equipe2Libelle": "Club B"
        }
        result = _process_single_match(match, "-18M", "1")

        assert result is not None
        assert result["team_1_score"] is None
        assert result["team_2_score"] is None

    def test_process_match_with_empty_scores(self):
        match = {
            "date": "2025-01-15T14:30:00",
            "equipe1Libelle": "Club A",
            "equipe1Score": "",
            "equipe2Libelle": "Club B",
            "equipe2Score": ""
        }
        result = _process_single_match(match, "-18M", "1")

        assert result is not None
        assert result["team_1_score"] is None
        assert result["team_2_score"] is None


class TestExtractMatchesFromSoup:
    """Tests pour l'extraction des matchs depuis le HTML."""

    def test_extract_matches_success(self):
        html = '''
        <html>
            <smartfire-component name="competitions---rencontre-list" attributes='{"rencontres": [{"date": "2025-01-15T14:30:00", "equipe1Libelle": "Club A", "equipe1Score": "25", "equipe2Libelle": "Club B", "equipe2Score": "22"}]}'></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_matches_from_soup(soup, "-18M", "1")

        assert len(result) == 1
        assert result[0]["team_1_name"] == "Club A"

    def test_extract_matches_no_component(self):
        html = '<html><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_matches_from_soup(soup, "-18M", "1")

        assert result == []

    def test_extract_matches_multiple(self):
        html = '''
        <html>
            <smartfire-component name="competitions---rencontre-list" attributes='{"rencontres": [{"date": "2025-01-15T14:30:00", "equipe1Libelle": "Club A", "equipe1Score": "25", "equipe2Libelle": "Club B", "equipe2Score": "22"}, {"date": "2025-01-15T16:30:00", "equipe1Libelle": "Club C", "equipe1Score": "30", "equipe2Libelle": "Club D", "equipe2Score": "28"}]}'></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_matches_from_soup(soup, "-18M", "1")

        assert len(result) == 2


class TestExtractPaginationMeta:
    """Tests pour l'extraction des métadonnées de pagination."""

    def test_extract_pagination_with_poule_selector(self):
        html = '''
        <html>
            <smartfire-component name="competitions---poule-selector" attributes='{"journees": [{"journeeNumero": "1"}, {"journeeNumero": "2"}]}'></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_pagination_meta(soup, "-18M")

        assert len(result) == 2

    def test_extract_pagination_with_journee_selector(self):
        html = '''
        <html>
            <smartfire-component name="competitions---journee-selector" attributes='{"journees": [{"journeeNumero": "1"}]}'></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_pagination_meta(soup, "-18M")

        assert len(result) == 1

    def test_extract_pagination_no_selector(self):
        html = '<html><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_pagination_meta(soup, "-18M")

        assert result == []

    def test_extract_pagination_with_poule_nested(self):
        html = '''
        <html>
            <smartfire-component name="competitions---poule-selector" attributes='{"poule": {"journees": [{"journeeNumero": "1"}]}}'></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_pagination_meta(soup, "-18M")

        assert len(result) == 1


class TestGetMatchesFromUrl:
    """Tests pour l'orchestrateur principal."""

    @patch("src.scraping.get_match_results.fetch_html")
    @patch("src.scraping.get_match_results.get_ranking_from_api")
    def test_get_matches_from_url_success(self, mock_ranking_api, mock_fetch_html):
        html = '''
        <html>
            <body>
                <smartfire-component name="competitions---rencontre-list" attributes='{"rencontres": [{"date": "2025-01-15T14:30:00", "equipe1Libelle": "Club A", "equipe1Score": "25", "equipe2Libelle": "Club B", "equipe2Score": "22"}]}'></smartfire-component>
                <smartfire-component name="competitions---journee-selector" attributes='{"journees": [{"journeeNumero": "1"}]}'></smartfire-component>
            </body>
        </html>
        '''
        mock_fetch_html.return_value = html
        mock_ranking_api.return_value = ("Excellence", [{"team_name": "Team A", "rank": 1}])

        matches, journees, ranking = get_matches_from_url("http://test.com/journee-1/", "-18M")

        assert len(matches) == 1
        assert len(journees) == 1
        assert len(ranking) == 1
        assert ranking[0]["official_phase_name"] == "Excellence"

    @patch("src.scraping.get_match_results.fetch_html")
    def test_get_matches_from_url_fetch_failure(self, mock_fetch_html):
        mock_fetch_html.return_value = None

        matches, journees, ranking = get_matches_from_url("http://test.com/", "-18M")

        assert matches == []
        assert journees == []
        assert ranking == []


class TestFetchHtml:
    """Tests pour la récupération du HTML."""

    @patch("src.scraping.get_match_results.requests.get")
    @patch("src.scraping.get_match_results.get_rate_limiter")
    def test_fetch_html_success(self, mock_limiter, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_html("http://test.com")

        assert result == "<html><body>Test</body></html>"

    @patch("src.scraping.get_match_results.requests.get")
    @patch("src.scraping.get_match_results.get_rate_limiter")
    def test_fetch_html_network_error(self, mock_limiter, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        result = fetch_html("http://test.com")

        assert result is None


class TestProcessSingleMatchFfhbIds:
    """Identifiants FFHB (AEK-56) : clé d'upsert du match et identité des équipes."""

    # Extrait réel de la poule 169284 (journée 3), champs utiles uniquement
    RAW = {
        "id": "1960241",
        "ext_rencontreId": "2390866",
        "equipe1Id": "1240516",
        "equipe2Id": "1240523",
        "date": "2025-10-04T21:00:00+02:00",
        "equipe1Libelle": "ALES CEVENNES HB",
        "equipe2Libelle": "LUNEL MARSILLARGUES HBC",
        "equipe1Score": "27",
        "equipe2Score": "23",
    }

    def test_ids_are_extracted(self):
        result = _process_single_match(dict(self.RAW), "SG", "3")
        assert result["match_id"] == "2390866"
        assert result["team_1_id"] == "1240516"
        assert result["team_2_id"] == "1240523"

    def test_match_id_is_ext_rencontre_id_not_internal_id(self):
        """Seul ext_rencontreId fonctionne dans l'URL publique .../rencontre-<id>/."""
        result = _process_single_match(dict(self.RAW), "SG", "3")
        assert result["match_id"] != self.RAW["id"]

    def test_missing_ids_are_none(self):
        match = {"date": "2025-10-04T21:00:00+02:00", "equipe1Libelle": "A", "equipe2Libelle": "B"}
        result = _process_single_match(match, "SG", "3")
        assert result["match_id"] is None
        assert result["team_1_id"] is None
        assert result["team_2_id"] is None

    def test_match_link_no_longer_produced(self):
        result = _process_single_match(dict(self.RAW), "SG", "3")
        assert "match_link" not in result
