"""Extraction du ``ModelSnapshot`` depuis l'API BIMData (lecture)."""

from __future__ import annotations

import sys

from bim_core.model_snapshot import ModelSnapshot

from .client import BIMDataReadClient


def extract_snapshot(client: BIMDataReadClient) -> ModelSnapshot:
    """Récupère le modèle complet depuis BIMData.

    Les routes BIMData retournent parfois 404 quand l'aspect n'est pas indexé par
    le moteur (modèle non finalisé, etc.) ; on tolère ces erreurs pour produire un
    snapshot partiel — mais on les **attache** au snapshot (``extraction_errors``,
    C2) *et* on les journalise sur stderr, pour qu'un snapshot partiel ne soit pas
    confondu avec un modèle vide par le consommateur (audit).
    """
    errors: list[str] = []

    def safe(label, fn, default):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}: {e}")
            return default

    snap = ModelSnapshot(
        project=safe("get_project", client.get_project, {}),
        model=safe("get_model", client.get_model, {}),
        sites=safe("get_sites", client.get_sites, []),
        buildings=safe("get_buildings", client.get_buildings, []),
        storeys=safe("get_storeys", client.get_storeys, []),
        spaces=safe("get_spaces", client.get_spaces, []),
        zones=safe("get_zones", client.get_zones, []),
        elements=safe("get_raw_elements", client.get_raw_elements, []),
        structure_tree=safe("get_structure_tree", client.get_structure_tree, []),
        extraction_errors=errors,
    )
    if errors:
        print(
            f"⚠ extract_snapshot: {len(errors)} route(s) BIMData en erreur :",
            file=sys.stderr,
        )
        for msg in errors:
            print(f"   • {msg}", file=sys.stderr)
    return snap.index()
