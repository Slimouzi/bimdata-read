"""Tests offline de bimdata-read : auth, dénormalisation, snapshot, cache.

Aucun appel réseau : le client est testé sur sa construction/auth, et
l'extraction/cache via un faux client (canned data).
"""

from __future__ import annotations

import bimdata_read as br
import pytest
from bimdata_read.client import BIMDataReadClient, _denormalize_raw_elements

# ── Auth (construction, sans réseau) ─────────────────────────────────────────


def test_auth_header_access_token_precedence():
    c = BIMDataReadClient(base_url="https://api.bimdata.io", access_token="tok", api_key="key")
    assert c.session.headers["Authorization"] == "Bearer tok"


def test_auth_header_api_key():
    c = BIMDataReadClient(base_url="https://api.bimdata.io/", api_key="key")
    assert c.session.headers["Authorization"] == "ApiKey key"
    assert c.base_url == "https://api.bimdata.io"  # trailing slash stripped


def test_auth_missing_raises():
    with pytest.raises(ValueError):
        BIMDataReadClient(base_url="https://api.bimdata.io")


def test_url_and_paths():
    c = BIMDataReadClient(
        base_url="https://api.bimdata.io", api_key="k", cloud_id=1, project_id=2, model_id=3
    )
    assert c._url("/x") == "https://api.bimdata.io/x"
    assert c._model_path("/storey") == "/cloud/1/project/2/model/3/storey"


# ── BCF topics & Smart Views (lecture seule, filtrage par format) ────────────


def _topics_client(monkeypatch, response):
    c = BIMDataReadClient(base_url="https://api.bimdata.io", api_key="k", project_id=42)
    calls = []

    def _fake_get(path, params=None):
        calls.append((path, params))
        return response

    monkeypatch.setattr(c, "_get", _fake_get)
    return c, calls


def test_list_bcf_topics_filters_standard_server_side(monkeypatch):
    # Le filtrage est CÔTÉ SERVEUR via ?format=standard (l'endpoint sans param
    # ne renvoie pas les Smart Views — vérifié contre l'API réelle).
    c, calls = _topics_client(monkeypatch, [{"title": "T"}])
    assert c.list_bcf_topics() == [{"title": "T"}]
    assert calls == [("/bcf/2.1/projects/42/topics", {"format": "standard"})]


def test_list_smart_views_filters_smartview_server_side(monkeypatch):
    c, calls = _topics_client(monkeypatch, [{"title": "SV"}])
    assert c.list_smart_views() == [{"title": "SV"}]
    assert calls == [("/bcf/2.1/projects/42/topics", {"format": "bimdata-smartview"})]


def test_list_project_topics_merges_both_formats(monkeypatch):
    c, calls = _topics_client(monkeypatch, [{"title": "X"}])
    res = c.list_project_topics()
    assert len(res) == 2  # standard + smartview concaténés
    assert [p for _, p in calls] == [{"format": "standard"}, {"format": "bimdata-smartview"}]


# ── Dénormalisation /element/raw ─────────────────────────────────────────────

_RAW = {
    "definitions": [
        {"name": "Name", "value_type": "string"},
        {"name": "LongName", "value_type": "string"},
        {"name": "Superficie calculée", "value_type": "number"},
    ],
    "property_sets": [
        {
            "name": "Attributes",
            "type": "attr",
            "properties": [{"def_id": 0, "value": "CH1"}, {"def_id": 1, "value": "CHAMBRE"}],
        },
        {
            "name": "AC_Pset_Marque_de_zone",
            "type": "pset",
            "properties": [{"def_id": 2, "value": 12.98}],
        },
    ],
    "layers": [{"name": "221 - MURS - Extérieurs périphériques.Exndo"}],
    "classifications": [{"code": "B2010", "system": "uniformat"}],
    "materials": {"materials_data": [{"name": "Béton"}]},
    "elements": [
        {
            "uuid": "u1",
            "type": "IfcSpace",
            "attributes": 0,
            "psets": [1],
            "layers": [0],
            "classifications": [0],
            "material_list": [0],
        },
    ],
}


def test_denormalize_inlines_everything():
    out = _denormalize_raw_elements(_RAW)
    assert len(out) == 1
    el = out[0]
    assert el["uuid"] == "u1" and el["type"] == "IfcSpace"
    assert el["name"] == "CH1" and el["longname"] == "CHAMBRE"
    # pset métier inliné
    assert el["property_sets"][0]["name"] == "AC_Pset_Marque_de_zone"
    assert el["property_sets"][0]["properties"][0]["value"] == 12.98
    # layer / classification / material résolus par index
    assert el["layers"][0]["name"].startswith("221 - MURS")
    assert el["classifications"][0]["code"] == "B2010"
    assert el["material_list"][0]["material"]["name"] == "Béton"


def test_denormalize_tolerates_garbage():
    assert _denormalize_raw_elements(None) == []
    assert _denormalize_raw_elements({"elements": []}) == []


# ── extract_snapshot avec faux client ────────────────────────────────────────


class _FakeClient:
    cloud_id, project_id, model_id = 1, 2, 3

    def get_project(self):
        return {"name": "I3F"}

    def get_model(self):
        return {"name": "M.ifc", "modified_date": "2026-07-01"}

    def get_sites(self):
        return [{"uuid": "site1", "name": "S"}]

    def get_buildings(self):
        return [{"uuid": "b1"}]

    def get_storeys(self):
        return [{"uuid": "st1", "name": "RDC"}]

    def get_spaces(self):
        return [{"uuid": "sp1", "name": "CHAMBRE"}]

    def get_zones(self):
        return [{"uuid": "z1", "name": "LGT-1"}]

    def get_raw_elements(self):
        return [{"uuid": "e1", "type": "IfcWall"}]

    def get_structure_tree(self):
        return [{"uuid": "proj", "type": "IfcProject", "children": []}]


def test_extract_snapshot_indexes():
    snap = br.extract_snapshot(_FakeClient())
    assert snap.summary()["n_spaces"] == 1
    assert snap.of_class("IfcWall")[0]["uuid"] == "e1"
    assert snap.element_by_uuid["site1"]["type"] == "IfcSite"


def test_extract_snapshot_tolerates_route_error():
    class _Broken(_FakeClient):
        def get_zones(self):
            raise RuntimeError("404")

    snap = br.extract_snapshot(_Broken())
    assert snap.summary()["n_zones"] == 0  # partial snapshot, no crash
    assert snap.summary()["n_spaces"] == 1
    # C2 — l'échec de route est **attaché** au snapshot (pas seulement sur stderr).
    assert snap.extraction_errors
    assert any("get_zones" in e for e in snap.extraction_errors)


def test_partial_snapshot_is_not_cached(tmp_path):
    # C2 — un snapshot partiel (route en échec) ne doit PAS être mis en cache :
    # sinon son vide se resservirait indéfiniment. Le 2e appel reste un miss.
    class _Broken(_FakeClient):
        def get_raw_elements(self):
            raise RuntimeError("401")

    client = _Broken()
    snap1, hit1 = br.cached_extract_snapshot(client, cache_dir=tmp_path)
    assert hit1 is False and snap1.extraction_errors
    _snap2, hit2 = br.cached_extract_snapshot(client, cache_dir=tmp_path)
    assert hit2 is False  # toujours un miss : rien n'a été mis en cache


# ── Cache ────────────────────────────────────────────────────────────────────


def test_cache_roundtrip(tmp_path):
    snap = br.extract_snapshot(_FakeClient())
    key = dict(cloud_id=1, project_id=2, model_id=3, model_modified_date="2026-07-01")
    br.save_snapshot_to_cache(snap, cache_dir=tmp_path, **key)
    loaded = br.load_snapshot_from_cache(cache_dir=tmp_path, **key)
    assert loaded is not None
    assert loaded.summary()["n_spaces"] == 1
    # clé différente (modèle ré-uploadé) → miss
    assert (
        br.load_snapshot_from_cache(
            cache_dir=tmp_path,
            cloud_id=1,
            project_id=2,
            model_id=3,
            model_modified_date="2026-07-02",
        )
        is None
    )


def test_cached_extract_snapshot_hit_miss(tmp_path):
    client = _FakeClient()
    snap1, hit1 = br.cached_extract_snapshot(client, cache_dir=tmp_path)
    assert hit1 is False  # premier appel = miss
    snap2, hit2 = br.cached_extract_snapshot(client, cache_dir=tmp_path)
    assert hit2 is True  # second appel = hit
    assert snap2.summary()["n_spaces"] == snap1.summary()["n_spaces"]
