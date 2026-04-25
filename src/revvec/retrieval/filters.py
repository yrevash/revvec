"""Filter DSL compiler: persona + time + equipment → Actian FilterBuilder.

Every retrieval query goes through `build_filter()` so the same role/time/
equipment gating is applied consistently. Defaults: `state == "active"` so
candidate_pattern points (Phase-2 ClusterAgent) stay out of the retrieval
surface until promoted.
"""
from __future__ import annotations

from typing import Any, Iterable

from actian_vectorai import Field, FilterBuilder


# Only these entity types are surfaced to user-facing retrieval.
# Bookkeeping types (candidate_pattern / active_pattern / answer_cache /
# archived_pattern) exist for ClusterAgent + AnswerCache internal use and
# would otherwise pollute the query surface.
DEFAULT_CONTENT_ENTITY_TYPES: tuple[str, ...] = (
    "sop_page",
    "equipment_photo",
    "defect_photo",
    "sensor_window",
    "incident_report",
    "shift_note",
    "training_clip",
    "voice_note",
    "alarm_incident",
    # nasa_image_caption and ntrs_document intentionally EXCLUDED, both are
    # title-only points (no body text). They outrank sop_page (which has the
    # real PDF body text) on short queries, then the grounded LLM has nothing
    # to cite and says "not found". sop_page carries the same source URL +
    # full page text, so we lose nothing by dropping the title-only siblings.
)


def build_filter(
    *,
    persona: str | None = None,
    time_range_ms: tuple[int, int] | None = None,
    equipment_id: str | None = None,
    line_id: str | None = None,
    state: str | None = "active",
    modalities: Iterable[str] | None = None,
    entity_types: Iterable[str] | None = None,
    classifications: Iterable[str] | None = None,
) -> Any:
    """Compose an Actian Filter from persona-aware retrieval parameters.

    Passing `state=None` disables the active-only default (use when you want
    to see candidates).
    """
    fb = FilterBuilder()

    # Persona gate, DISABLED for Phase 3.
    # role_visibility is stored as a list in payload; Actian's SDK in this build
    # doesn't support list-contains filtering (any_of/eq both return 0 hits
    # against a list field). Rather than re-ingest with one-bool-per-persona
    # columns, we accept that retrieval is persona-agnostic at the filter layer
    # and do persona customisation at the prompt layer (Phase 4 LLM persona
    # templates). The `persona` kwarg is retained for forward-compat.
    _ = persona  # reserved; see note above

    if time_range_ms is not None:
        t0, t1 = time_range_ms
        fb = fb.must(Field("timestamp_ms").between(t0, t1))

    if equipment_id:
        fb = fb.must(Field("equipment_id").eq(equipment_id))

    if line_id:
        fb = fb.must(Field("line_id").eq(line_id))

    if state:
        fb = fb.must(Field("state").eq(state))

    if modalities:
        mods = list(modalities)
        if len(mods) == 1:
            fb = fb.must(Field("modality").eq(mods[0]))
        else:
            fb = fb.must(Field("modality").any_of(mods))

    ets = list(entity_types) if entity_types else list(DEFAULT_CONTENT_ENTITY_TYPES)
    if len(ets) == 1:
        fb = fb.must(Field("entity_type").eq(ets[0]))
    elif len(ets) > 1:
        fb = fb.must(Field("entity_type").any_of(ets))

    if classifications:
        cls = list(classifications)
        if len(cls) == 1:
            fb = fb.must(Field("classification").eq(cls[0]))
        else:
            fb = fb.must(Field("classification").any_of(cls))

    return fb.build()


# Pre-baked filters for the four personas, saves one call-site's worth of
# boilerplate in every retrieval codepath.

PERSONA_DEFAULTS = {
    "new_hire":       {"persona": "new_hire"},
    "maintenance":    {"persona": "maintenance"},
    "quality":        {"persona": "quality"},
    "plant_manager":  {"persona": "plant_manager"},
}


def build_persona_filter(persona: str, **overrides) -> Any:
    kwargs = dict(PERSONA_DEFAULTS.get(persona, {}))
    kwargs.update(overrides)
    return build_filter(**kwargs)
