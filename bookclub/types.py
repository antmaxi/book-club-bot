from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from typing import Any, Literal

Lang = Literal["en", "ru", "de"]
TranslationValue = str | Callable[..., str]
BookLike = sqlite3.Row | Mapping[str, Any]
