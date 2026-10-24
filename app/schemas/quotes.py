from typing import List

from pydantic import BaseModel, Field


class QuoteItem(BaseModel):
    dosya_adi: str = Field(min_length=1, max_length=255)
    ebat_metin: str = Field(min_length=1, max_length=100)
    kesim_metre: float = Field(ge=0, le=1_000_000)
    patlatma_adedi: int = Field(ge=0, le=1_000_000)
    birim_agirlik_kg: float = Field(ge=0, le=1_000_000)
    birim_sure_sn: float = Field(ge=0, le=1_000_000_000)
    adet: int = Field(ge=1, le=1_000_000)
    birim_satis_tl: float = Field(ge=0, le=1_000_000_000)


class BatchPDFRequest(BaseModel):
    atolye_adi: str = Field(min_length=1, max_length=200)
    musteri_adi: str = Field(default="", max_length=200)
    teklif_notu: str = Field(default="", max_length=1000)
    malzeme_adi: str = Field(min_length=1, max_length=200)
    kalinlik_mm: float = Field(gt=0, le=1000)
    kesim_gazi: str = Field(min_length=1, max_length=100)
    kdv_orani: float = Field(ge=0, le=100)
    kalemler: List[QuoteItem] = Field(min_items=1, max_items=200)
