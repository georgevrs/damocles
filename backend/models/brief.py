"""Brief — the final intelligence output, structured for the citation chain.

Every BriefSection that makes a factual claim must list at least one
``citation_node_ids`` entry. The frontend resolves each citation to a
``SourceNode`` via the citation chain endpoint — that resolution is what
powers the gold-medal demo moment.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SectionType(str, Enum):
    BLUF = "BLUF"
    KEY_JUDGMENT = "KEY_JUDGMENT"
    SUPPORTING = "SUPPORTING"
    DEVILS_ADVOCATE = "DEVILS_ADVOCATE"
    RECOMMENDATION = "RECOMMENDATION"


class Urgency(str, Enum):
    ROUTINE = "ROUTINE"
    PRIORITY = "PRIORITY"
    IMMEDIATE = "IMMEDIATE"


class BriefSection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    section_type: SectionType
    text: str
    citation_node_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    agent_source: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class Brief(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    watch_id: str
    bluf: BriefSection
    key_judgments: list[BriefSection] = Field(default_factory=list)
    supporting_evidence: list[BriefSection] = Field(default_factory=list)
    devils_advocate: BriefSection | None = None
    recommendation: BriefSection | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def all_sections(self) -> list[BriefSection]:
        out = [self.bluf, *self.key_judgments, *self.supporting_evidence]
        if self.devils_advocate:
            out.append(self.devils_advocate)
        if self.recommendation:
            out.append(self.recommendation)
        return out


class SourceNode(BaseModel):
    """A graph node resolved for the citation chain endpoint.

    ``raw_evidence`` holds the original artifact (SAR tile bytes b64,
    article URL, Telegram message text). ``map_highlight`` and
    ``graph_highlight`` drive the corresponding panels in the UI.
    """
    node_id: str
    node_type: str  # "Vessel" | "NewsEvent" | "SocialSignal" | "CompositeEvent"
    properties: dict[str, Any] = Field(default_factory=dict)
    raw_evidence: dict[str, Any] = Field(default_factory=dict)
    map_highlight: dict[str, Any] = Field(default_factory=dict)
    graph_highlight: dict[str, Any] = Field(default_factory=dict)


class CitationChain(BaseModel):
    """Returned by the citation chain endpoint when a judge clicks a sentence."""
    section: BriefSection
    source_nodes: list[SourceNode] = Field(default_factory=list)
    corroboration_chain: list[dict[str, Any]] = Field(default_factory=list)
    confidence_breakdown: dict[str, Any] = Field(default_factory=dict)


# ─── Supervisor LLM output schema ────────────────────────────────────────────
# Mapped onto Brief on the server side. The LLM doesn't generate UUIDs or
# watch_ids — those are filled in after parsing.
class SupervisorBriefSection(BaseModel):
    """The shape each text-bearing block in the supervisor's JSON output takes."""
    text: str
    citation_node_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    agent_source: str = ""


class SupervisorRecommendation(BaseModel):
    text: str
    urgency: Urgency = Urgency.ROUTINE
    citation_node_ids: list[str] = Field(default_factory=list)


class SupervisorDevilsAdvocate(BaseModel):
    text: str
    devil_confidence: float = Field(ge=0.0, le=1.0)
    citation_node_ids: list[str] = Field(default_factory=list)


class SupervisorOutput(BaseModel):
    """Pydantic mirror of the JSON the SupervisorAgent's LLM call must produce.

    Mapped to ``Brief`` (with watch_id, brief_id, BriefSection IDs added) by
    ``SupervisorAgent.assemble_brief()``.
    """
    bluf: SupervisorBriefSection
    key_judgments: list[SupervisorBriefSection] = Field(default_factory=list)
    supporting_evidence: list[SupervisorBriefSection] = Field(default_factory=list)
    devils_advocate: SupervisorDevilsAdvocate | None = None
    recommended_action: SupervisorRecommendation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def all_text_bearing_sections(self) -> list[SupervisorBriefSection | SupervisorDevilsAdvocate | SupervisorRecommendation]:
        """All sub-blocks that contain factual text — every one needs citations."""
        out: list = [self.bluf, *self.key_judgments, *self.supporting_evidence]
        if self.devils_advocate is not None:
            out.append(self.devils_advocate)
        if self.recommended_action is not None:
            out.append(self.recommended_action)
        return out
