"""Client HTTP BIMData **lecture seule**, config-agnostique.

Extrait du noyau de lecture de ``audit-bim-i3f`` (``BIMDataClient``). Ne porte
que la lecture (métadonnées, hiérarchie spatiale, éléments dénormalisés) — aucune
écriture (BCF, Smart Views, classifications, propertysets restent dans le MCP
d'écriture).

Authentification — ordre de précédence (paramètres explicites, pas de lecture
d'environnement ni de ``config`` applicatif) :

1. ``access_token`` (header ``Authorization: Bearer …``),
2. ``api_key`` (header ``Authorization: ApiKey …``),
3. flow OAuth2 ``client_credentials`` (``client_id`` + ``client_secret`` +
   ``iam_url``).
"""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def _build_retry_adapter() -> HTTPAdapter:
    """``HTTPAdapter`` avec retries bornés sur 429 / 5xx + backoff exponentiel.

    Politique : 3 tentatives totales, backoff 0.5 s × 2ⁿ (cap urllib3 ~8 s).
    Respecte ``Retry-After`` (utile sur les 429 BIMData).

    **Méthodes idempotentes uniquement** (``GET`` / ``HEAD``) — cohérent avec un
    client de lecture.
    """
    retry = Retry(
        total=3,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    return HTTPAdapter(max_retries=retry)


class BIMDataAuthError(PermissionError):
    """L'API BIMData a rejeté la requête pour cause d'auth (401 / 403).

    Sous-classe de ``PermissionError`` pour découpler les couches supérieures du
    module ``requests``.
    """


# Valeurs du query param / champ ``format`` d'un topic BCF : ``standard`` = issue
# BCF classique, ``bimdata-smartview`` = Smart View (panneau dédié du viewer).
BCF_FORMAT = "standard"
SMARTVIEW_FORMAT = "bimdata-smartview"


class BIMDataReadClient:
    """Client HTTP **lecture seule** pour l'API BIMData.

    Couvre la lecture du modèle (snapshot spatial + dénormalisation
    ``/element/raw``). L'instance porte la cible (cloud/project/model) et la
    session HTTP authentifiée. Aucune méthode d'écriture.

    Exemple:
        >>> client = BIMDataReadClient(
        ...     base_url="https://api.bimdata.io",
        ...     cloud_id=..., project_id=..., model_id=..., api_key="...",
        ... )
        >>> client.get_buildings()      # GET /cloud/.../building
        [...]

    Attributes:
        base_url: Racine de l'API (sans ``/v1``).
        cloud_id, project_id, model_id: Cible IFC. ``None`` autorisé tant qu'on
            n'appelle pas les routes ``/model/...``.
        api_key, access_token, client_id, client_secret, iam_url: modes d'auth.
        timeout: Timeout HTTP par défaut, en secondes.
        session: ``requests.Session`` avec le header ``Authorization`` injecté.
    """

    def __init__(
        self,
        *,
        base_url: str,
        cloud_id: int | str | None = None,
        project_id: int | str | None = None,
        model_id: int | str | None = None,
        api_key: str | None = None,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        iam_url: str | None = None,
        timeout: int = 60,
    ):
        """Initialise le client et la session HTTP.

        Raises:
            ValueError: Si aucun mode d'authentification n'est disponible
                (ni ``access_token``, ni ``api_key``, ni
                ``client_id + client_secret``).
        """
        self.base_url = base_url.rstrip("/")
        self.cloud_id = cloud_id
        self.project_id = project_id
        self.model_id = model_id
        self.api_key = api_key
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.iam_url = iam_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self._auth_headers())
        adapter = _build_retry_adapter()
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ── Auth ────────────────────────────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Construit le header ``Authorization`` selon l'ordre de précédence.

        Raises:
            ValueError: Si aucun mode d'auth n'est dispo.
        """
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        if self.api_key:
            return {"Authorization": f"ApiKey {self.api_key}"}
        if self.client_id and self.client_secret:
            token = self._fetch_oauth_token()
            self.access_token = token
            return {"Authorization": f"Bearer {token}"}
        raise ValueError(
            "Authentification BIMData manquante : passer access_token, api_key, "
            "ou (client_id + client_secret)."
        )

    def _fetch_oauth_token(self) -> str:
        """Acquiert un Bearer token via OAuth2 ``client_credentials``.

        Raises:
            ValueError: Si ``iam_url`` n'est pas fourni.
            requests.HTTPError: Si l'IAM rejette les credentials.
        """
        if not self.iam_url:
            raise ValueError("iam_url requis pour le flow OAuth2 client_credentials.")
        resp = requests.post(
            self.iam_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ── HTTP helpers ────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        """Compose l'URL absolue depuis un chemin relatif à ``base_url``."""
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: dict | None = None) -> Any:
        """GET authentifié + décode JSON.

        Raises:
            BIMDataAuthError: Statut 401/403 (token invalide ou périmé).
            requests.HTTPError: Autres statuts 4xx/5xx.
        """
        resp = self.session.get(self._url(path), params=params, timeout=self.timeout)
        if resp.status_code in (401, 403):
            raise BIMDataAuthError(f"BIMData {resp.status_code} on {path}")
        resp.raise_for_status()
        return resp.json()

    # ── Routes ──────────────────────────────────────────────────────────────

    def _project_path(self, suffix: str = "") -> str:
        """Compose le chemin ``/cloud/{cloud}/project/{project}{suffix}``."""
        return f"/cloud/{self.cloud_id}/project/{self.project_id}{suffix}"

    def _model_path(self, suffix: str = "") -> str:
        """Compose ``/cloud/{cloud}/project/{project}/model/{model}{suffix}``."""
        return f"{self._project_path()}/model/{self.model_id}{suffix}"

    # Métadonnées
    def get_project(self) -> dict:
        """Récupère les métadonnées du projet BIMData."""
        return self._get(self._project_path())

    def get_model(self) -> dict:
        """Récupère les métadonnées du modèle IFC."""
        return self._get(self._model_path())

    # Hiérarchie spatiale
    def get_buildings(self) -> list:
        """Liste les ``IfcBuilding`` du modèle."""
        return self._get(self._model_path("/building"))

    def get_building_detail(self, uuid: str) -> dict:
        """Détail d'un bâtiment (avec ``IfcPostalAddress`` si présente)."""
        return self._get(self._model_path(f"/building/{uuid}"))

    def get_storeys(self) -> list:
        """Liste les ``IfcBuildingStorey`` (étages) du modèle."""
        return self._get(self._model_path("/storey"))

    def get_spaces(self) -> list:
        """Liste les ``IfcSpace`` (pièces) du modèle."""
        return self._get(self._model_path("/space"))

    def get_zones(self) -> list:
        """Liste les ``IfcZone`` du modèle (logements, parties communes)."""
        return self._get(self._model_path("/zone"))

    def get_sites(self) -> list:
        """Liste les ``IfcSite`` du modèle (via ``/element?type=IfcSite``)."""
        return self._get(self._model_path("/element"), params={"type": "IfcSite"})

    # Éléments (route optimisée + dénormalisation)
    def get_raw_elements(self) -> list:
        """Récupère tous les éléments via ``/element/raw`` puis dénormalise.

        La route ``/element/raw`` renvoie une forme normalisée (psets, layers,
        classifications, materials référencés par index). On inline tout sur
        chaque élément — format attendu par les couches d'analyse.
        """
        raw = self._get(self._model_path("/element/raw"))
        return _denormalize_raw_elements(raw)

    def get_structure_tree(self) -> list:
        """Arborescence spatiale (Project → Site → Building → Storey → …).

        Récupère ``structure_file`` sur le modèle puis télécharge le JSON depuis
        le bucket. Liste vide si le modèle n'a pas encore généré son fichier.
        """
        model = self.get_model()
        url = model.get("structure_file")
        if not url:
            return []
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── BCF Topics & Smart Views (lecture seule) ────────────────────────────
    # BCF issues et Smart Views sont servies par le MÊME endpoint topics, mais le
    # **filtrage est côté serveur** via le query param ``format`` : sans param, le
    # endpoint ne renvoie que les issues ``standard`` (les Smart Views n'y sont
    # PAS). On DOIT donc passer ``?format=…`` (vérifié contre l'API réelle).

    def _list_topics(self, fmt: str) -> list:
        """``GET /bcf/2.1/projects/{project}/topics?format={fmt}``."""
        return self._get(f"/bcf/2.1/projects/{self.project_id}/topics", params={"format": fmt})

    def list_bcf_topics(self) -> list:
        """Issues **BCF** du projet (``format=standard``)."""
        return self._list_topics(BCF_FORMAT)

    def list_smart_views(self) -> list:
        """**Smart Views** du projet (``format=bimdata-smartview``)."""
        return self._list_topics(SMARTVIEW_FORMAT)

    def list_project_topics(self) -> list:
        """**Tous** les topics du projet (issues BCF + Smart Views concaténées)."""
        return self.list_bcf_topics() + self.list_smart_views()


def _denormalize_raw_elements(raw: dict) -> list[dict]:
    """Dénormalise la réponse ``/element/raw`` de BIMData.

    L'API renvoie une structure normalisée (psets, layers, classifications,
    materials, definitions dans des tables parallèles, référencés par index).
    On inline tout sur chaque élément.

    Args:
        raw: Réponse brute de ``/element/raw``.

    Returns:
        Liste de dicts dénormalisés, un par élément. Liste vide si ``raw`` est
        ``None`` ou malformé.
    """
    if not isinstance(raw, dict):
        return raw or []

    defs = raw.get("definitions") or []
    psets_table = raw.get("property_sets") or []
    layers_table = raw.get("layers") or []
    classifs_table = raw.get("classifications") or []
    materials_table = (raw.get("materials") or {}).get("materials_data") or []

    def expand_pset(idx):
        if not isinstance(idx, int) or not (0 <= idx < len(psets_table)):
            return None
        p = psets_table[idx]
        properties = []
        for prop in p.get("properties") or []:
            di = prop.get("def_id")
            df = defs[di] if isinstance(di, int) and 0 <= di < len(defs) else {}
            properties.append(
                {
                    "definition": {
                        "name": df.get("name"),
                        "value_type": df.get("value_type"),
                    },
                    "value": prop.get("value"),
                }
            )
        return {
            "name": p.get("name"),
            "type": p.get("type"),
            "description": p.get("description"),
            "properties": properties,
        }

    def by_index(table, indices):
        return [table[i] for i in (indices or []) if isinstance(i, int) and 0 <= i < len(table)]

    out = []
    for el in raw.get("elements") or []:
        attr_pset = expand_pset(el.get("attributes"))
        attr_lookup = {}
        if attr_pset:
            for prop in attr_pset["properties"]:
                nm = (prop.get("definition") or {}).get("name")
                if nm:
                    attr_lookup[nm] = prop.get("value")

        psets_inlined = [p for p in (expand_pset(i) for i in (el.get("psets") or [])) if p]
        material_list = [
            {"material": {"name": materials_table[i].get("name")}}
            for i in (el.get("material_list") or [])
            if isinstance(i, int) and 0 <= i < len(materials_table)
        ]

        out.append(
            {
                "uuid": el.get("uuid"),
                "type": el.get("type"),
                "name": attr_lookup.get("Name"),
                "description": attr_lookup.get("Description"),
                "longname": attr_lookup.get("LongName"),
                "object_type": attr_lookup.get("ObjectType"),
                "attributes": attr_pset,
                "property_sets": psets_inlined,
                "classifications": by_index(classifs_table, el.get("classifications")),
                "layers": by_index(layers_table, el.get("layers")),
                "material_list": material_list,
            }
        )
    return out
