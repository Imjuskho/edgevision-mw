from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FeatureFlagsSchema(BaseModel):
    liveAnnotate: bool = True
    training: bool = True
    export: bool = True
    fleet: bool = True
    roadAnalysis: bool = True
    agriAnalysis: bool = True
    dedup: bool = True
    roadTaxonomy: bool = True
    agriTaxonomy: bool = True
    healthDashboard: bool = True
    trajectoryPrediction: bool = True
    anomalyDetection: bool = True
    sceneReconstruction: bool = True


class PersonalSettingsSchema(BaseModel):
    theme: str = "dark"
    showDashboardHealth: bool = True
    expertMode: bool = False
    compactSidebar: bool = False
    reducedMotion: bool = False
    sidebarCollapsed: bool = False
    defaultZoom: float = Field(default=1.0, ge=0.5, le=3.0)
    onboardingComplete: bool = False


class OperationalSettingsSchema(BaseModel):
    features: FeatureFlagsSchema = Field(default_factory=FeatureFlagsSchema)
    dedupDefaultThreshold: float = Field(default=0.92, ge=0.8, le=0.99)
    dedupDefaultMethods: list[str] = Field(default_factory=lambda: ["phash", "clip"])


class UserSettingsResponse(BaseModel):
    personal: PersonalSettingsSchema
    operational: OperationalSettingsSchema
    role: str
    synced: bool = True


class UserSettingsPatch(BaseModel):
    personal: PersonalSettingsSchema | None = None
    operational: OperationalSettingsSchema | None = None


def default_settings_for_role(role: str) -> dict[str, Any]:
    """Role-based defaults — annotators get a simplified feature set."""
    personal = PersonalSettingsSchema().model_dump()
    operational = OperationalSettingsSchema().model_dump()

    if role == "ANNOTATOR":
        operational["features"] = FeatureFlagsSchema(
            liveAnnotate=False,
            training=False,
            export=False,
            fleet=False,
            roadAnalysis=False,
            agriAnalysis=False,
            dedup=False,
            roadTaxonomy=False,
            agriTaxonomy=False,
            healthDashboard=False,
            trajectoryPrediction=False,
            anomalyDetection=False,
            sceneReconstruction=False,
        ).model_dump()
        personal["showDashboardHealth"] = False
    elif role in ("ADMIN", "QA"):
        pass  # full defaults
    elif role == "OPERATOR":
        operational["features"] = FeatureFlagsSchema(
            liveAnnotate=False,
            roadAnalysis=False,
            agriAnalysis=False,
            roadTaxonomy=False,
            agriTaxonomy=False,
            healthDashboard=False,
        ).model_dump()
    else:
        operational["features"] = FeatureFlagsSchema(
            liveAnnotate=False,
            training=False,
            export=False,
            fleet=False,
            roadAnalysis=False,
            agriAnalysis=False,
            dedup=False,
            roadTaxonomy=False,
            agriTaxonomy=False,
            healthDashboard=False,
            trajectoryPrediction=False,
            anomalyDetection=False,
            sceneReconstruction=False,
        ).model_dump()

    return {"personal": personal, "operational": operational}
