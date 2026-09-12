"""Madde kayıt defteri: YAML'dan 66 maddeyi yükler ve doğrular."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

REGISTRY_PATH = Path(__file__).parent / "items.yaml"

SourceType = Literal["analysis", "special", "news", "unavailable"]


class ItemSpec(BaseModel):
    id: int
    title_tr: str
    description_tr: str | None = None
    category: str
    source: str = Field(description="analysis:<key> | special:<name> | news | unavailable")
    query: str | None = None
    keywords: list[str] = Field(default_factory=list)
    weight: float = 1.0
    note: str | None = None

    @property
    def source_type(self) -> str:
        return self.source.split(":", 1)[0]

    @property
    def source_ref(self) -> str | None:
        parts = self.source.split(":", 1)
        return parts[1] if len(parts) > 1 else None


@lru_cache
def load_registry(path: str | None = None) -> list[ItemSpec]:
    file_path = Path(path) if path else REGISTRY_PATH
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    items = [ItemSpec.model_validate(entry) for entry in data["items"]]
    ids = [item.id for item in items]
    if len(items) != 66 or len(set(ids)) != 66 or set(ids) != set(range(1, 67)):
        raise ValueError(
            f"Kayıt defteri 1..66 arasında benzersiz 66 madde icermeli; bulunan: {len(items)}"
        )
    return items


def registry_summary() -> list[dict]:
    return [
        {
            "id": item.id,
            "title": item.title_tr,
            "description": item.description_tr,
            "category": item.category,
            "source": item.source,
            "source_type": item.source_type,
            "query": item.query,
            "weight": item.weight,
            "note": item.note,
        }
        for item in load_registry()
    ]
