import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import MAX_DXF_FILE_SIZE, MAX_FILES_PER_REQUEST, UPLOAD_CHUNK_SIZE
from app.schemas.quotes import BatchPDFRequest
from app.services.dxf import parse_dxf_geometry
from app.services.pdf import generate_corporate_pdf
from app.services.samples import ensure_sample_dxfs


router = APIRouter()


@router.post("/api/dxf-analiz")
async def analyze_uploaded_dxfs(files: List[UploadFile] = File(...)):
    results = []
    try:
        if len(files) > MAX_FILES_PER_REQUEST:
            raise HTTPException(
                status_code=413,
                detail=f"Tek istekte en fazla {MAX_FILES_PER_REQUEST} DXF dosyası yüklenebilir.",
            )

        for uploaded_file in files:
            filename = uploaded_file.filename or ""
            if Path(filename).suffix.casefold() != ".dxf":
                continue

            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as temp_file:
                    temp_path = temp_file.name
                    total_size = 0
                    while chunk := await uploaded_file.read(UPLOAD_CHUNK_SIZE):
                        total_size += len(chunk)
                        if total_size > MAX_DXF_FILE_SIZE:
                            raise HTTPException(
                                status_code=413,
                                detail=f"{Path(filename).name}: Dosya boyutu 10 MB sınırını aşıyor.",
                            )
                        temp_file.write(chunk)
                if total_size == 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{Path(filename).name}: Dosya boş.",
                    )
                results.append(
                    await run_in_threadpool(parse_dxf_geometry, temp_path, filename)
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail=f"{Path(filename).name} analiz edilemedi: {error}",
                ) from error
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
    finally:
        for uploaded_file in files:
            await uploaded_file.close()

    if not results:
        raise HTTPException(status_code=400, detail="Geçerli bir .dxf dosyası bulunamadı.")
    return {"durum": "basarili", "parcalar": results}


@router.get("/api/ornek-10-parca")
async def get_sample_10_parts():
    try:
        sample_files = ensure_sample_dxfs()
        results = []
        for path, name in sample_files:
            results.append(
                await run_in_threadpool(parse_dxf_geometry, str(path), name)
            )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=f"Örnek DXF dosyaları hazırlanamadı: {error}") from error
    return {"durum": "basarili", "parcalar": results}


@router.get("/api/test-dxf-zip-indir")
async def download_sample_zip():
    try:
        sample_files = ensure_sample_dxfs()
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, name in sample_files:
                archive.write(path, arcname=name)
    except (OSError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=500, detail=f"Örnek DXF paketi oluşturulamadı: {error}") from error
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Sariguzel_Teklif_10_Ornek_DXF.zip"},
    )


@router.post("/api/kurumsal-pdf-indir")
def download_corporate_pdf(request: BatchPDFRequest):
    return generate_corporate_pdf(request)
