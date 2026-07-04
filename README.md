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
