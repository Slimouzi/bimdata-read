"""bimdata-read — noyau de LECTURE de l'API BIMData.

Client HTTP lecture seule + extraction/cache du ``ModelSnapshot`` (contrat défini
dans ``bim-core``). Aucune écriture BIMData, aucune règle métier I3F.
"""

from __future__ import annotations

from .cache import (
    cached_extract_snapshot,
    load_snapshot_from_cache,
    save_snapshot_to_cache,
)
from .client import BIMDataAuthError, BIMDataReadClient
from .snapshot import extract_snapshot

__all__ = [
    "BIMDataReadClient",
    "BIMDataAuthError",
    "extract_snapshot",
    "cached_extract_snapshot",
    "save_snapshot_to_cache",
    "load_snapshot_from_cache",
]

__version__ = "0.1.1"
