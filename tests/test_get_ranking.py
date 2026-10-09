from bs4 import BeautifulSoup

from src.scraping.get_ranking import (
    parse_ffhb_id,
    parse_ranking_list,
    extract_ranking_from_soup,
    _find_ranking_candidates,
    _is_valid_ranking_list,
)


class TestParseRankingList:
    """Tests pour la fonction de parsing du classement."""

    def test_parse_with_teamName(self):
        """Parse une liste avec la clé teamName."""
        ranking_list = [
            {"teamName": "Club A", "rank": 1, "points": 15, "won": 5, "lost": 0, "draws": 0},
            {"teamName": "Club B", "rank": 2, "points": 12, "won": 4, "lost": 1, "draws": 0},
        ]
        result = parse_ranking_list(ranking_list)

        assert len(result) == 2
        assert result[0]["team_name"] == "Club A"
        assert result[0]["rank"] == 1
        assert result[0]["points"] == 15
        assert result[1]["team_name"] == "Club B"

    def test_parse_with_label(self):
        """Parse une liste avec la clé label."""
        ranking_list = [
            {"label": "Equipe X", "place": 1, "pts": 10, "won": 3, "lost": 2},
        ]
        result = parse_ranking_list(ranking_list)

        assert len(result) == 1
        assert result[0]["team_name"] == "Equipe X"
        assert result[0]["points"] == 10

    def test_parse_with_equipeLibelle(self):
        """Parse une liste avec la clé equipeLibelle."""
        ranking_list = [
            {"equipeLibelle": "Club Y", "rang": 3, "point": 8, "gagne": 2, "perdu": 3},
        ]
        result = parse_ranking_list(ranking_list)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club Y"
        assert result[0]["points"] == 8

    def test_parse_with_nested_team(self):
        """Parse une liste avec team.name imbriqué."""
        ranking_list = [
            {"team": {"name": "Club Z"}, "sortOrder": 1, "pts": 20},
        ]
        result = parse_ranking_list(ranking_list)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club Z"

    def test_parse_calculates_matches_played(self):
        """Calcule les matchs joués si absent."""
        ranking_list = [
            {"teamName": "Club A", "won": 5, "lost": 3, "draws": 2},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["matches_played"] == 10

    def test_parse_with_explicit_matches_played(self):
        """Utilise matches_played si présent."""
        ranking_list = [
            {"teamName": "Club A", "won": 5, "lost": 3, "draws": 2, "matchesPlayed": 8},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["matches_played"] == 8

    def test_parse_handles_goal_difference(self):
        """Parse la différence de but."""
        ranking_list = [
            {"teamName": "Club A", "goalDifference": 15},
            {"teamName": "Club B", "diff": -3},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["goal_diff"] == 15
        assert result[1]["goal_diff"] == -3

    def test_parse_handles_goals_for_against(self):
        """Parse les buts pour et contre."""
        ranking_list = [
            {"teamName": "Club A", "goalsFor": 100, "goalsAgainst": 80},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["goals_for"] == 100
        assert result[0]["goals_against"] == 80

    def test_parse_strips_whitespace(self):
        """Supprime les espaces autour du nom."""
        ranking_list = [
            {"teamName": "  Club A  ", "rank": 1},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["team_name"] == "Club A"

    def test_parse_skips_invalid_rows(self):
        """Ignore les lignes sans nom d'équipe."""
        ranking_list = [
            {"rank": 1, "points": 10},
            {"teamName": "Club A", "rank": 2},
        ]
        result = parse_ranking_list(ranking_list)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club A"

    def test_parse_with_string_numbers(self):
        """Convertit les nombres en strings."""
        ranking_list = [
            {"teamName": "Club A", "rank": "1", "points": "15"},
        ]
        result = parse_ranking_list(ranking_list)

        assert result[0]["rank"] == 1
        assert result[0]["points"] == 15

    def test_parse_empty_list(self):
        """Gère une liste vide."""
        result = parse_ranking_list([])
        assert result == []


class TestFindRankingCandidates:
    """Tests pour la recherche de candidats au classement."""

    def test_finds_ranking_key(self):
        """Trouve une clé 'ranking'."""
        data = {"ranking": [{"teamName": "A"}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1
        assert any(r == [{"teamName": "A"}] for r in result)

    def test_finds_rows_key(self):
        """Trouve une clé 'rows'."""
        data = {"rows": [{"teamName": "B"}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1

    def test_finds_classification_key(self):
        """Trouve une clé 'classification'."""
        data = {"classification": [{"teamName": "C"}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1

    def test_finds_standings_key(self):
        """Trouve une clé 'standings'."""
        data = {"standings": [{"teamName": "D"}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1

    def test_finds_classements_key(self):
        """Trouve une clé 'classements'."""
        data = {"classements": [{"teamName": "E"}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1

    def test_searches_nested_dict(self):
        """Cherche dans les dictionnaires imbriqués."""
        data = {"outer": {"ranking": [{"teamName": "F"}]}}
        result = _find_ranking_candidates(data)
        assert len(result) >= 1

    def test_handles_non_dict_input(self):
        """Gère les entrées non-dictionnaire."""
        result = _find_ranking_candidates("string")
        assert result == []

    def test_handles_list_input(self):
        """Gère une liste en entrée (retourne vide car pas un dict)."""
        data = [{"teamName": "A"}]
        result = _find_ranking_candidates(data)
        assert result == []

    def test_finds_multiple_candidates(self):
        """Trouve plusieurs candidats."""
        data = {"ranking": [{"a": 1}], "rows": [{"b": 2}]}
        result = _find_ranking_candidates(data)
        assert len(result) >= 2


class TestIsValidRankingList:
    """Tests pour la validation d'une liste de classement."""

    def test_valid_list_with_teamName_and_points(self):
        """Valide une liste avec teamName et points."""
        data = [{"teamName": "A", "points": 10}]
        assert _is_valid_ranking_list(data) is True

    def test_valid_list_with_label_and_rank(self):
        """Valide une liste avec label et rank."""
        data = [{"label": "A", "rank": 1}]
        assert _is_valid_ranking_list(data) is True

    def test_valid_list_with_equipeLibelle_and_pts(self):
        """Valide une liste avec equipeLibelle et pts."""
        data = [{"equipeLibelle": "A", "pts": 5}]
        assert _is_valid_ranking_list(data) is True

    def test_valid_list_with_won(self):
        """Valide une liste avec won."""
        data = [{"teamName": "A", "won": 3}]
        assert _is_valid_ranking_list(data) is True

    def test_invalid_empty_list(self):
        """Rejette une liste vide."""
        assert _is_valid_ranking_list([]) is False

    def test_invalid_not_dict(self):
        """Rejette une liste de non-dictionnaires."""
        assert _is_valid_ranking_list([1, 2, 3]) is False

    def test_invalid_no_name(self):
        """Rejette une liste sans nom d'équipe."""
        data = [{"points": 10, "rank": 1}]
        assert _is_valid_ranking_list(data) is False

    def test_invalid_no_stats(self):
        """Rejette une liste sans statistiques."""
        data = [{"teamName": "A"}]
        assert _is_valid_ranking_list(data) is False


class TestExtractRankingFromSoup:
    """Tests pour l'extraction du classement depuis le HTML."""

    def test_extract_from_valid_component(self):
        """Extrait depuis un composant smartfire valide."""
        html = '''
        <html>
            <smartfire-component
                attributes="{&quot;ranking&quot;: [{&quot;teamName&quot;: &quot;Club A&quot;, &quot;rank&quot;: 1, &quot;points&quot;: 15}]}">
            </smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club A"

    def test_extract_finds_nested_ranking(self):
        """Trouve le classement dans des données imbriquées."""
        html = '''
        <html>
            <smartfire-component
                attributes="{&quot;data&quot;: {&quot;ranking&quot;: [{&quot;teamName&quot;: &quot;Club B&quot;, &quot;rank&quot;: 2, &quot;points&quot;: 10}]}}">
            </smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club B"

    def test_extract_returns_empty_when_no_ranking(self):
        """Retourne une liste vide si pas de classement."""
        html = '<html><smartfire-component attributes="{&quot;other&quot;: []}"></smartfire-component></html>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert result == []

    def test_extract_returns_empty_on_invalid_json(self):
        """Gère les JSON invalides."""
        html = '<html><smartfire-component attributes="not-valid-json"></smartfire-component></html>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert result == []

    def test_extract_handles_multiple_components(self):
        """Parcourt plusieurs composants."""
        html = '''
        <html>
            <smartfire-component name="header" attributes="{&quot;data&quot;: {&quot;ranking&quot;: [{&quot;teamName&quot;: &quot;First&quot;, &quot;rank&quot;: 1, &quot;points&quot;: 10}]}}"></smartfire-component>
            <smartfire-component name="footer" attributes="{&quot;rows&quot;: [{&quot;teamName&quot;: &quot;Second&quot;, &quot;rank&quot;: 2, &quot;points&quot;: 8}]}}"></smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert len(result) == 1
        assert result[0]["team_name"] == "First"

    def test_extract_handles_empty_components(self):
        """Gère les composants sans attributs."""
        html = '<html><smartfire-component></smartfire-component></html>'
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert result == []

    def test_extract_with_rows_key(self):
        """Extrait depuis la clé 'rows'."""
        html = '''
        <html>
            <smartfire-component
                attributes="{&quot;rows&quot;: [{&quot;teamName&quot;: &quot;Club C&quot;, &quot;rank&quot;: 1, &quot;points&quot;: 20}]}">
            </smartfire-component>
        </html>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        result = extract_ranking_from_soup(soup)

        assert len(result) == 1
        assert result[0]["team_name"] == "Club C"


class TestParseFfhbId:
    """Normalisation des identifiants FFHB."""

    def test_string_id(self):
        assert parse_ffhb_id("1240516") == "1240516"

    def test_int_id_becomes_string(self):
        assert parse_ffhb_id(1240516) == "1240516"

    def test_none_and_empty_are_none(self):
        assert parse_ffhb_id(None) is None
        assert parse_ffhb_id("") is None
        assert parse_ffhb_id("  ") is None


class TestParseRankingTeamId:
    """equipeId du classement : même référentiel que equipe1Id / equipe2Id des matchs (AEK-56)."""

    def test_team_id_extracted(self):
        rows = [{"equipeId": "1240523", "equipe_libelle": "LUNEL MARSILLARGUES HBC", "place": "3", "point": "30"}]
        assert parse_ranking_list(rows)[0]["team_id"] == "1240523"

    def test_team_id_missing_is_none(self):
        rows = [{"teamName": "Team A", "rank": 1, "points": 10}]
        assert parse_ranking_list(rows)[0]["team_id"] is None
