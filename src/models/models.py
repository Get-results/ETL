from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_serializer


class MatchIngest(BaseModel):
    """
    Représente le payload JSON attendu par POST /api/ingest/matches.
    Miroir de MatchIngestDto côté Spring Boot.
    """

    match_date: datetime
    match_id: Optional[str] = Field(None, description="ID FFHB de la rencontre (ext_rencontreId), clé d'upsert")
    team_1_id: Optional[str] = Field(None, description="ID FFHB de l'équipe 1 (equipe1Id)")
    team_1_name: str = Field(..., description="Nom de l'équipe 1")
    team_1_score: Optional[int] = None
    team_2_id: Optional[str] = Field(None, description="ID FFHB de l'équipe 2 (equipe2Id)")
    team_2_name: str = Field(..., description="Nom de l'équipe 2")
    team_2_score: Optional[int] = None
    category: str = Field(..., description="Clé de pivot pour le backend (ex: -18M)")
    pool_id: str = Field(..., description="ID technique de la poule (source)")
    official_phase_name: Optional[str] = None
    round: Optional[str] = None

    @field_serializer("match_date", when_used="json")
    def serialize_match_date(self, v: datetime) -> str:
        return v.strftime("%Y-%m-%dT%H:%M:%S")


class RankingIngest(BaseModel):
    """
    Représente le payload JSON attendu par POST /api/ingest/rankings.
    Miroir de RankingIngestDto côté Spring Boot.
    """

    pool_id: str = Field(..., description="ID technique de la poule (source)")
    category: str = Field(..., description="Clé de pivot pour le backend (ex: -18M)")
    team_id: Optional[str] = Field(None, description="ID FFHB de l'équipe (equipeId), même référentiel que team_1_id / team_2_id")
    team_name: str = Field(..., description="Nom de l'équipe")
    rank_number: int = Field(..., description="Position au classement")
    points: int = Field(default=0, description="Points totaux")
    matches_played: int = Field(default=0, description="Matchs joués")
    won: int = Field(default=0, description="Matchs gagnés")
    draws: int = Field(default=0, description="Matchs nuls")
    lost: int = Field(default=0, description="Matchs perdus")
    goal_diff: int = Field(default=0, description="Différence de buts")
    official_phase_name: Optional[str] = None
