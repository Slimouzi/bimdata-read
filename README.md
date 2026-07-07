# bimdata-read

Noyau de **lecture** de l'API BIMData, extrait du MCP `audit-bim-i3f`.

Fournit :
- `BIMDataReadClient` — client HTTP **lecture seule** (métadonnées projet/modèle,
  hiérarchie spatiale, éléments `/element/raw` dénormalisés). Config-agnostique :
  `base_url` + auth passés en paramètres, aucune dépendance à un `config`
  applicatif.
- `extract_snapshot(client)` → `ModelSnapshot` (contrat défini dans `bim-core`).
- Cache local gzip versionné : `cached_extract_snapshot`, `save_snapshot_to_cache`,
  `load_snapshot_from_cache`.

**Hors périmètre** (par conception) : toute écriture BIMData (BCF, Smart Views,
classifications, propertysets) — réservée à un futur MCP « BIMData Write » — et
les règles métier ArchiCAD/I3F (normalisation LongName→Name, etc.), qui restent
dans `audit-bim-i3f`.

## Versions

- **v0.1.3** — release courante. Filtrage des topics BCF **côté serveur** via le
  query param `?format=…` : `list_bcf_topics` (`standard`), `list_smart_views`
  (`bimdata-smartview`), `list_project_topics` (concaténation). Vérifié contre
  l'API réelle : sans `?format`, le serveur **n'inclut pas** les Smart Views.
- **⚠️ v0.1.2 — NE PAS UTILISER.** Le tag `bimdata-read-v0.1.2` a été **déplacé**
  après publication (violation de « never move published tags ») : les lockfiles
  existants restent épinglés sur le commit *pré-correctif* (`497c6058`, filtrage
  client-side) où `list_smart_views()` renvoie toujours `0`. La correction a été
  **re-publiée proprement en v0.1.3** (tag immuable). Épingler **v0.1.3**.
- **v0.1.1 / v0.1.0** — antérieures (pas de filtrage `?format` fiable).

## Dépendances

`bim-core` (contrat `ModelSnapshot`, résolu via tag Git — non publié sur PyPI) et
`requests`.

## Installation (dev)

```bash
pip install "git+https://github.com/Slimouzi/bim-core.git@bim-core-v0.1.0"
pip install -e /path/to/bimdata-read
```

## Provenance & parité

Extrait de `audit-bim-i3f` (référence gelée `legacy-i3f-mcp-v1`). Le découpage
préserve la parité : mêmes routes, même dénormalisation, même cache, même
`ModelSnapshot`.
