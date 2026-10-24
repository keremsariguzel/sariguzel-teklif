import math
import tempfile
import os
import io
import zipfile
from datetime import datetime
from typing import List
import ezdxf
import networkx as nx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI(title="Sarıgüzel Teklif | Endüstriyel Lazer Kesim SaaS", version="4.0.0")

# Türkçe Font Desteği
FONT_REG = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
for font_dir in ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"]:
    reg_path = os.path.join(font_dir, "DejaVuSans.ttf")
    bold_path = os.path.join(font_dir, "DejaVuSans-Bold.ttf")
    if os.path.exists(reg_path) and os.path.exists(bold_path):
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", reg_path))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
            FONT_REG = "DejaVu"
            FONT_BOLD = "DejaVu-Bold"
            break
        except Exception:
            pass

def tr_safe(text: str) -> str:
    if FONT_REG == "DejaVu":
        return str(text)
    tr_map = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    return str(text).translate(tr_map)

SAMPLE_DIR = "/home/kerem/test_dxf"

def ensure_sample_dxfs():
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    parts = [
        (
            "01_DN100_Boru_Flansi.dxf",
            [(110 + 100 * math.cos(math.radians(a)), 110 + 100 * math.sin(math.radians(a))) for a in range(0, 360, 15)],
            [(110, 110, 48)] + [(110 + 78 * math.cos(math.radians(a)), 110 + 78 * math.sin(math.radians(a)), 9) for a in range(0, 360, 45)]
        ),
        (
            "02_NEMA23_Motor_Braketi.dxf",
            [(0,0), (220,0), (220,160), (170,160), (170,200), (50,200), (50,160), (0,160)],
            [(110, 80, 38.1), (60, 35, 6), (160, 35, 6), (60, 125, 6), (160, 125, 6), (80, 180, 8), (140, 180, 8)]
        ),
        (
            "03_Agir_Sasi_Taban_Plakasi.dxf",
            [(0,0), (320,0), (320,220), (0,220)],
            [(35, 35, 14), (285, 35, 14), (285, 185, 14), (35, 185, 14), (110, 110, 35), (210, 110, 35)]
        ),
        (
            "04_Menfez_Havalandirma_Sac.dxf",
            [(0,0), (420,0), (420,140), (0,140)],
            [(25, 25, 6), (395, 25, 6), (395, 115, 6), (25, 115, 6)] + [(70 + i * 45, 70, 14) for i in range(7)]
        ),
        (
            "05_Kose_Takviye_Guseli.dxf",
            [(0,0), (240,0), (240,45), (45,240), (0,240)],
            [(55, 55, 24), (125, 45, 15), (45, 125, 15), (185, 30, 8), (30, 185, 8)]
        ),
        (
            "06_Hidrolik_Valf_Plakasi.dxf",
            [(0,0), (260,0), (260,180), (0,180)],
            [(65, 90, 22), (130, 90, 28), (195, 90, 22), (25, 25, 9), (235, 25, 9), (235, 155, 9), (25, 155, 9)]
        ),
        (
            "07_Konveyor_Rulman_Yatagi.dxf",
            [(30,0), (190,0), (220,30), (220,150), (190,180), (30,180), (0,150), (0,30)],
            [(110, 90, 42), (45, 45, 10), (175, 45, 10), (175, 135, 10), (45, 135, 10)]
        ),
        (
            "08_Elektrik_Pano_Kapagi.dxf",
            [(0,0), (500,0), (500,360), (0,360)],
            [(250, 220, 65), (120, 90, 18), (200, 90, 18), (280, 90, 18), (360, 90, 18), (30, 30, 7), (470, 30, 7), (470, 330, 7), (30, 330, 7)]
        ),
        (
            "09_T_Sasi_Baglanti_Plakasi.dxf",
            [(60,0), (160,0), (160,90), (220,90), (220,170), (0,170), (0,90), (60,90)],
            [(110, 35, 12), (110, 75, 12), (40, 130, 12), (110, 130, 16), (180, 130, 12)]
        ),
        (
            "10_Suspansiyon_Baglanti_Braketi.dxf",
            [(0,20), (20,0), (160,0), (180,20), (180,140), (140,180), (40,180), (0,140)],
            [(90, 110, 32), (45, 40, 10), (135, 40, 10), (45, 145, 8), (135, 145, 8)]
        )
    ]

    paths = []
    for name, poly, holes in parts:
        p = os.path.join(SAMPLE_DIR, name)
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_lwpolyline(poly, close=True)
        for cx, cy, r in holes:
            msp.add_circle((cx, cy), radius=r)
        doc.saveas(p)
        paths.append((p, name))
    return paths

def parse_dxf_geometry(file_path: str, filename: str):
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    total_cut_length = 0.0
    standalone_pierces = 0
    G = nx.Graph()

    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    svg_elements = []
    pierce_markers = []

    def update_bounds(x, y):
        nonlocal min_x, min_y, max_x, max_y
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)

    def pt_key(x, y):
        return (round(x, 2), round(y, 2))

    for entity in msp:
        dxftype = entity.dxftype()

        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            total_cut_length += math.hypot(e.x - s.x, e.y - s.y)
            G.add_edge(pt_key(s.x, s.y), pt_key(e.x, e.y))
            update_bounds(s.x, s.y)
            update_bounds(e.x, e.y)
            svg_elements.append(
                f'<line x1="{s.x:.2f}" y1="{-s.y:.2f}" x2="{e.x:.2f}" y2="{-e.y:.2f}" stroke="#f97316" stroke-width="2" vector-effect="non-scaling-stroke" />'
            )

        elif dxftype == "CIRCLE":
            c, r = entity.dxf.center, entity.dxf.radius
            total_cut_length += 2 * math.pi * r
            standalone_pierces += 1
            update_bounds(c.x - r, c.y - r)
            update_bounds(c.x + r, c.y + r)
            svg_elements.append(
                f'<circle cx="{c.x:.2f}" cy="{-c.y:.2f}" r="{r:.2f}" fill="#38bdf8" fill-opacity="0.06" stroke="#38bdf8" stroke-width="1.8" vector-effect="non-scaling-stroke" />'
            )
            pierce_markers.append((c.x + r, -c.y))

        elif dxftype == "ARC":
            r = entity.dxf.radius
            sa = math.radians(entity.dxf.start_angle)
            ea = math.radians(entity.dxf.end_angle)
            diff = (ea - sa) % (2 * math.pi)
            total_cut_length += r * diff

            sx = entity.dxf.center.x + r * math.cos(sa)
            sy = entity.dxf.center.y + r * math.sin(sa)
            ex = entity.dxf.center.x + r * math.cos(ea)
            ey = entity.dxf.center.y + r * math.sin(ea)

            G.add_edge(pt_key(sx, sy), pt_key(ex, ey))
            update_bounds(sx, sy)
            update_bounds(ex, ey)

            large_arc = 1 if diff > math.pi else 0
            svg_elements.append(
                f'<path d="M {sx:.2f} {-sy:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 0 {ex:.2f} {-ey:.2f}" fill="none" stroke="#f97316" stroke-width="2" vector-effect="non-scaling-stroke" />'
            )

        elif dxftype in ("LWPOLYLINE", "POLYLINE"):
            try:
                pts = entity.get_points("xy") if dxftype == "LWPOLYLINE" else [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            except Exception:
                pts = []
            if pts:
                poly_len = 0.0
                pts_svg = []
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i + 1]
                    poly_len += math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    update_bounds(p1[0], p1[1])
                    pts_svg.append(f"{p1[0]:.2f},{-p1[1]:.2f}")
                update_bounds(pts[-1][0], pts[-1][1])
                pts_svg.append(f"{pts[-1][0]:.2f},{-pts[-1][1]:.2f}")

                pts_str = " ".join(pts_svg)
                if entity.is_closed:
                    p1, p2 = pts[-1], pts[0]
                    poly_len += math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    svg_elements.append(
                        f'<polygon points="{pts_str}" fill="#f97316" fill-opacity="0.05" stroke="#f97316" stroke-width="2.2" vector-effect="non-scaling-stroke" />'
                    )
                else:
                    svg_elements.append(
                        f'<polyline points="{pts_str}" fill="none" stroke="#f97316" stroke-width="2.2" vector-effect="non-scaling-stroke" />'
                    )
                total_cut_length += poly_len
                standalone_pierces += 1
                pierce_markers.append((pts[0][0], -pts[0][1]))

    if min_x == float("inf"):
        min_x, max_x, min_y, max_y = 0.0, 100.0, 0.0, 100.0

    for comp in nx.connected_components(G):
        first_pt = next(iter(comp))
        pierce_markers.append((first_pt[0], -first_pt[1]))

    connected_contours = nx.number_connected_components(G)
    total_pierce_count = max(standalone_pierces + connected_contours, 1)

    kesim_metre = total_cut_length / 1000.0
    w = max(max_x - min_x, 0.1)
    h = max(max_y - min_y, 0.1)

    pad = max(w, h) * 0.10 + 4.0
    vb_x = min_x - pad
    vb_y = -max_y - pad
    vb_w = max(w + 2 * pad, 1.0)
    vb_h = max(h + 2 * pad, 1.0)

    dot_r = max(w, h) * 0.014
    dots_svg = [
        f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{dot_r:.2f}" fill="#10b981" />'
        for px, py in pierce_markers[:60]
    ]

    svg_raw = (
        f'<svg viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" xmlns="http://www.w3.org/2000/svg" class="w-full h-full max-h-60">'
        + "".join(svg_elements)
        + "".join(dots_svg)
        + "</svg>"
    )

    return {
        "dosya_adi": filename,
        "genislik_mm": round(w, 1),
        "boy_mm": round(h, 1),
        "ebat_metin": f"{w:.1f} x {h:.1f} mm",
        "kesim_metre": round(kesim_metre, 3),
        "patlatma_adedi": total_pierce_count,
        "adet": 1,
        "svg_cizim": svg_raw
    }

@app.post("/api/dxf-analiz")
async def analyze_uploaded_dxfs(files: List[UploadFile] = File(...)):
    sonuclar = []
    for f in files:
        if not f.filename.lower().endswith(".dxf"):
            continue
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp:
                tmp.write(await f.read())
                tmp_path = tmp.name
            geom = parse_dxf_geometry(tmp_path, f.filename)
            sonuclar.append(geom)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"{f.filename} okunamadı: {str(e)}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    if not sonuclar:
        raise HTTPException(status_code=400, detail="Geçerli bir .dxf dosyası bulunamadı.")
    return {"durum": "basarili", "parcalar": sonuclar}

@app.get("/api/ornek-10-parca")
async def get_sample_10_parts():
    sample_files = ensure_sample_dxfs()
    sonuclar = [parse_dxf_geometry(path, name) for path, name in sample_files]
    return {"durum": "basarili", "parcalar": sonuclar}

@app.get("/api/test-dxf-zip-indir")
async def download_sample_zip():
    sample_files = ensure_sample_dxfs()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, name in sample_files:
            zf.write(path, arcname=name)
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=Sariguzel_Teklif_10_Ornek_DXF.zip"}
    )

class QuoteItem(BaseModel):
    dosya_adi: str
    ebat_metin: str
    kesim_metre: float
    patlatma_adedi: int
    birim_agirlik_kg: float
    birim_sure_sn: float
    adet: int
    birim_satis_tl: float

class BatchPDFRequest(BaseModel):
    atolye_adi: str
    musteri_adi: str
    teklif_notu: str
    malzeme_adi: str
    kalinlik_mm: float
    kesim_gazi: str
    kdv_orani: float
    kalemler: List[QuoteItem]

@app.post("/api/kurumsal-pdf-indir")
async def generate_corporate_pdf(req: BatchPDFRequest):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    tarih_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    teklif_no = f"SRG-{datetime.now().strftime('%Y%m%d-%H%M')}"

    # Üst Kurumsal Banner
    p.setFillColor(colors.HexColor("#090d16"))
    p.rect(0, height - 95, width, 95, fill=True, stroke=False)
    p.setFillColor(colors.HexColor("#f97316"))
    p.rect(0, height - 99, width, 4, fill=True, stroke=False)

    p.setFillColor(colors.white)
    p.setFont(FONT_BOLD, 19)
    p.drawString(35, height - 42, tr_safe(req.atolye_adi.upper() or "SARIGÜZEL TEKLİF LAZER & SAC METAL"))
    p.setFont(FONT_REG, 9)
    p.setFillColor(colors.HexColor("#94a3b8"))
    p.drawString(35, height - 60, tr_safe("Endüstriyel CNC Lazer Kesim, Sac İşleme ve Mühendislik Teklif Formu"))
    p.drawString(35, height - 74, tr_safe("CAD/CAM Otomatik Maliyet ve Kesim Analiz Raporu"))

    p.setFillColor(colors.HexColor("#f97316"))
    p.setFont(FONT_BOLD, 11)
    p.drawRightString(width - 35, height - 42, tr_safe(f"TEKLİF NO: {teklif_no}"))
    p.setFillColor(colors.white)
    p.setFont(FONT_REG, 9)
    p.drawRightString(width - 35, height - 58, tr_safe(f"Tarih: {tarih_str}"))
    p.drawRightString(width - 35, height - 72, tr_safe("Opsiyon / Geçerlilik: 7 İş Günü"))

    # Müşteri ve Teknik Parametre Kutusu
    y = height - 125
    p.setFillColor(colors.HexColor("#f8fafc"))
    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.rect(35, y - 42, width - 70, 54, fill=True, stroke=True)

    p.setFillColor(colors.HexColor("#0f172a"))
    p.setFont(FONT_BOLD, 10)
    p.drawString(45, y - 6, tr_safe(f"Müşteri / Firma: {req.musteri_adi or 'Sayın Yetkili'}"))
    p.setFont(FONT_REG, 9)
    p.setFillColor(colors.HexColor("#334155"))
    p.drawString(45, y - 22, tr_safe(f"Malzeme Kalitesi: {req.malzeme_adi}   |   Kalınlık: {req.kalinlik_mm} mm   |   Kesim Gazı: {req.kesim_gazi}"))
    p.setFillColor(colors.HexColor("#64748b"))
    p.drawString(45, y - 35, tr_safe(f"Not / Teslimat: {req.teklif_notu or 'Fabrika teslim, standart lazer kesim toleranslarında (ISO 9013).'}"))

    # Tablo Başlığı
    y -= 66
    p.setFillColor(colors.HexColor("#1e293b"))
    p.rect(35, y - 6, width - 70, 22, fill=True, stroke=False)
    p.setFillColor(colors.white)
    p.setFont(FONT_BOLD, 8)
    p.drawString(41, y + 2, "#")
    p.drawString(58, y + 2, tr_safe("PARÇA / DXF DOSYA ADI"))
    p.drawString(205, y + 2, tr_safe("EBAT (mm)"))
    p.drawString(280, y + 2, tr_safe("KESİM / DELİK"))
    p.drawString(355, y + 2, tr_safe("BİRİM KG"))
    p.drawString(405, y + 2, tr_safe("ADET"))
    p.drawRightString(490, y + 2, tr_safe("BİRİM FİYAT"))
    p.drawRightString(width - 40, y + 2, tr_safe("TOPLAM TUTAR"))

    y -= 22
    ara_toplam = 0.0
    toplam_agirlik = 0.0
    toplam_adet = 0
    toplam_sure_sn = 0.0

    p.setFont(FONT_REG, 8)
    for idx, item in enumerate(req.kalemler, start=1):
        if y < 165:
            p.showPage()
            y = height - 60
            p.setFont(FONT_REG, 8)

        satir_toplam = item.birim_satis_tl * item.adet
        ara_toplam += satir_toplam
        toplam_agirlik += item.birim_agirlik_kg * item.adet
        toplam_adet += item.adet
        toplam_sure_sn += item.birim_sure_sn * item.adet

        if idx % 2 == 0:
            p.setFillColor(colors.HexColor("#f8fafc"))
            p.rect(35, y - 5, width - 70, 18, fill=True, stroke=False)

        p.setFillColor(colors.HexColor("#0f172a"))
        p.drawString(41, y, str(idx))
        p.drawString(58, y, tr_safe(item.dosya_adi[:25]))
        p.drawString(205, y, tr_safe(item.ebat_metin))
        p.drawString(280, y, tr_safe(f"{item.kesim_metre}m / {item.patlatma_adedi}d"))
        p.drawString(355, y, f"{item.birim_agirlik_kg:.2f} kg")
        p.drawString(408, y, f"{item.adet}")
        p.drawRightString(490, y, f"{item.birim_satis_tl:,.2f} TL")
        p.setFont(FONT_BOLD, 8)
        p.drawRightString(width - 40, y, f"{satir_toplam:,.2f} TL")
        p.setFont(FONT_REG, 8)

        p.setStrokeColor(colors.HexColor("#e2e8f0"))
        p.setLineWidth(0.5)
        p.line(35, y - 6, width - 35, y - 6)
        y -= 19

    kdv_tutari = ara_toplam * (req.kdv_orani / 100.0)
    genel_toplam = ara_toplam + kdv_tutari

    y -= 12
    # Sol Alt Teknik Özet Kutusu
    p.setFillColor(colors.HexColor("#f8fafc"))
    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.rect(35, y - 80, 260, 86, fill=True, stroke=True)
    p.setFont(FONT_BOLD, 9)
    p.setFillColor(colors.HexColor("#0f172a"))
    p.drawString(45, y - 12, tr_safe("ÜRETİM & LOJİSTİK ÖZETİ"))
    p.setFont(FONT_REG, 8.5)
    p.setFillColor(colors.HexColor("#475569"))
    p.drawString(45, y - 28, tr_safe(f"• Toplam Kalem / Parça Adedi: {len(req.kalemler)} Kalem ({toplam_adet} Adet)"))
    p.drawString(45, y - 43, tr_safe(f"• Toplam Brüt Sac Ağırlığı: {toplam_agirlik:.2f} kg"))
    p.drawString(45, y - 58, tr_safe(f"• Tahmini Lazer Kesim Süresi: {(toplam_sure_sn / 60.0):.1f} Dakika"))
    p.drawString(45, y - 73, tr_safe("• Ödeme Şekli: Sipariş onayında peşin / cari mutabakat"))

    # Sağ Alt Finansal Toplam Kutusu
    p.setFillColor(colors.HexColor("#f8fafc"))
    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.rect(width - 245, y - 80, 210, 86, fill=True, stroke=True)

    p.setFont(FONT_REG, 9)
    p.setFillColor(colors.HexColor("#475569"))
    p.drawString(width - 235, y - 18, tr_safe("Ara Toplam (KDV Hariç):"))
    p.drawRightString(width - 45, y - 18, f"{ara_toplam:,.2f} TL")

    p.drawString(width - 235, y - 36, tr_safe(f"Hesaplanan KDV (%{req.kdv_orani:.0f}):"))
    p.drawRightString(width - 45, y - 36, f"{kdv_tutari:,.2f} TL")

    p.setStrokeColor(colors.HexColor("#cbd5e1"))
    p.line(width - 235, y - 46, width - 45, y - 46)

    p.setFont(FONT_BOLD, 11)
    p.setFillColor(colors.HexColor("#ea580c"))
    p.drawString(width - 235, y - 66, tr_safe("GENEL TOPLAM:"))
    p.drawRightString(width - 45, y - 66, f"{genel_toplam:,.2f} TL")

    # İmza Alanları
    p.setFont(FONT_BOLD, 8.5)
    p.setFillColor(colors.HexColor("#334155"))
    p.drawString(60, 75, tr_safe("TEKLİF VEREN FİRMA ONAYI"))
    p.drawString(width - 210, 75, tr_safe("MÜŞTERİ SİPARİŞ ONAYI"))
    p.setFont(FONT_REG, 8)
    p.setFillColor(colors.HexColor("#94a3b8"))
    p.drawString(60, 60, tr_safe(req.atolye_adi))
    p.drawString(width - 210, 60, tr_safe("Kaşe / İmza / Tarih"))

    p.drawString(35, 25, tr_safe("* Bu resmi teklif formu Sarıgüzel Teklif CAD/CAM SaaS Motoru tarafından otomatik oluşturulmuştur."))

    p.showPage()
    p.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Sariguzel_Teklif_{teklif_no}.pdf"}
    )

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sarıgüzel Teklif | Endüstriyel CNC Lazer & Sac Metal SaaS</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #060911; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .blueprint-grid {
            background-color: #080d1a;
            background-image: 
                linear-gradient(to right, rgba(30, 41, 59, 0.35) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(30, 41, 59, 0.35) 1px, transparent 1px);
            background-size: 20px 20px;
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #f97316; }
    </style>
</head>
<body class="text-slate-100 min-h-screen selection:bg-orange-500 selection:text-white">

    <!-- ÜST KURUMSAL NAVBAR -->
    <div class="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur sticky top-0 z-30">
        <div class="max-w-[1440px] mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center space-x-3.5">
                <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-orange-500 via-orange-600 to-amber-700 flex items-center justify-center font-extrabold text-white text-xl shadow-lg shadow-orange-500/25 border border-orange-400/30">
                    ST
                </div>
                <div>
                    <div class="flex items-center space-x-2.5">
                        <h1 class="text-lg sm:text-xl font-extrabold tracking-tight text-white">
                            SARIGÜZEL <span class="text-orange-500">TEKLİF</span>
                        </h1>
                        <span class="text-[10px] font-mono font-semibold uppercase px-2 py-0.5 rounded-md bg-orange-500/10 text-orange-400 border border-orange-500/25">
                            CAD/CAM SaaS v4.0
                        </span>
                        <span class="hidden sm:inline-flex items-center text-[10px] font-mono px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            ● 0ms Canlı Motor Aktif
                        </span>
                    </div>
                    <p class="text-xs text-slate-400">2D DXF Geometrik Analiz, Dinamik Malzeme Matrisi ve Kurumsal Teklif Platformu</p>
                </div>
            </div>

            <!-- Kurumsal Sistem Durumu -->
            <div class="flex items-center space-x-3">
                <div class="bg-slate-900/90 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-300 font-mono flex items-center space-x-2">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span>ISO 9013 Hassas Kesim Motoru</span>
                </div>
            </div>
        </div>
    </div>

    <div class="max-w-[1440px] mx-auto px-4 sm:px-6 py-6 space-y-6">

        <!-- ÜST FİRMA & MÜŞTERİ BİLGİ BARI -->
        <div class="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 grid grid-cols-1 md:grid-cols-3 gap-4 shadow-lg">
            <div>
                <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Teklif Veren Atölye / Firma Adı</label>
                <input type="text" id="atolyeAdi" value="Sarıgüzel Lazer & Sac Metal San. Tic. Ltd. Şti." class="w-full bg-slate-950 border border-slate-800 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-medium outline-none transition">
            </div>
            <div>
                <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Müşteri / Alıcı Firma Ünvanı</label>
                <input type="text" id="musteriAdi" value="Anadolu Makina ve Savunma Sanayi A.Ş." placeholder="Müşteri Firma Adı" class="w-full bg-slate-950 border border-slate-800 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-medium outline-none transition">
            </div>
            <div>
                <label class="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Teslimat & Teklif Notu (PDF'te Görünür)</label>
                <input type="text" id="teklifNotu" value="3 iş günü içinde fabrika teslim. ISO 9013 standart lazer kesim." class="w-full bg-slate-950 border border-slate-800 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-slate-300 outline-none transition">
            </div>
        </div>

        <!-- 6'LI ENDÜSTRİYEL KPI KARTLARI -->
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5">
            <div class="bg-slate-900 border border-slate-800/90 rounded-xl p-3.5">
                <span class="text-[11px] font-medium text-slate-400 block">Toplam Kalem / Adet</span>
                <span id="kpiKalem" class="text-base font-extrabold text-white font-mono mt-1 block">0 Kalem (0 Adet)</span>
            </div>
            <div class="bg-slate-900 border border-slate-800/90 rounded-xl p-3.5">
                <span class="text-[11px] font-medium text-slate-400 block">Toplam Kesim & Delme</span>
                <span id="kpiKesim" class="text-base font-extrabold text-orange-400 font-mono mt-1 block">0.0 m / 0 delik</span>
            </div>
            <div class="bg-slate-900 border border-slate-800/90 rounded-xl p-3.5">
                <span class="text-[11px] font-medium text-slate-400 block">Toplam Lazer Süresi</span>
                <span id="kpiSure" class="text-base font-extrabold text-emerald-400 font-mono mt-1 block">0.0 dk</span>
            </div>
            <div class="bg-slate-900 border border-slate-800/90 rounded-xl p-3.5">
                <span class="text-[11px] font-medium text-slate-400 block">Toplam Brüt Ağırlık</span>
                <span id="kpiAgirlik" class="text-base font-extrabold text-sky-400 font-mono mt-1 block">0.00 kg</span>
            </div>
            <div class="bg-slate-900 border border-slate-800/90 rounded-xl p-3.5">
                <span class="text-[11px] font-medium text-slate-400 block">Net Atölye Kârı</span>
                <span id="kpiNetKar" class="text-base font-extrabold text-amber-400 font-mono mt-1 block">0.00 TL</span>
            </div>
            <div class="bg-gradient-to-br from-orange-950/90 via-slate-900 to-slate-900 border border-orange-500/40 rounded-xl p-3.5 shadow-lg shadow-orange-950/20">
                <span class="text-[11px] font-semibold text-orange-300 block">Genel Toplam (KDV Dahil)</span>
                <span id="kpiGenelToplam" class="text-lg font-extrabold text-orange-400 font-mono mt-0.5 block">0.00 TL</span>
            </div>
        </div>

        <!-- ANA ÇALIŞMA ALANI -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

            <!-- SOL PANEL: DOSYA YÜKLEME & MÜHENDİSLİK PARAMETRELERİ -->
            <div class="lg:col-span-4 space-y-5">

                <!-- 1. DXF YÜKLEME MERKEZİ -->
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
                    <div class="flex items-center justify-between">
                        <h2 class="text-xs font-extrabold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
                            <span class="w-2 h-2 rounded-full bg-orange-500"></span>
                            <span>1. CAD / DXF Yükleme Merkezi</span>
                        </h2>
                        <label class="flex items-center space-x-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
                            <input type="checkbox" id="appendMode" checked class="rounded bg-slate-950 border-slate-700 text-orange-500 focus:ring-0">
                            <span>Listeye Ekle Modu</span>
                        </label>
                    </div>

                    <div id="dropzone" class="border-2 border-dashed border-slate-700 hover:border-orange-500 rounded-xl p-5 text-center transition bg-slate-950/70">
                        <svg class="w-8 h-8 mx-auto text-orange-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                        </svg>
                        <p class="text-xs font-semibold text-slate-200 mb-3">DXF Dosyalarını Buraya Sürükleyin veya Seçin</p>
                        <input type="file" id="dxfFiles" accept=".dxf" multiple
                            class="block w-full text-xs text-slate-300 file:mr-3 file:py-2 file:px-3.5 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-orange-600 file:text-white hover:file:bg-orange-500 cursor-pointer bg-slate-900 border border-slate-800 rounded-lg p-1.5">
                    </div>
                </div>

                <!-- 2. MALZEME & LAZER KESİM MATRİSİ -->
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
                    <div class="flex items-center justify-between">
                        <h2 class="text-xs font-extrabold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
                            <span class="w-2 h-2 rounded-full bg-sky-500"></span>
                            <span>2. Malzeme & Lazer Matrisi</span>
                        </h2>
                        <span id="gasBadge" class="text-[11px] font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-500/30">
                            Gaz: O2 (Oksijen)
                        </span>
                    </div>

                    <div>
                        <label class="block text-xs font-medium text-slate-400 mb-1">Sac Malzeme Kalitesi</label>
                        <select id="malzemeTuru" class="w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs font-semibold text-white outline-none">
                            <option value="dkp">DKP / S235JR (St37 Siyah Sac - 7.85 g/cm³)</option>
                            <option value="s355">S355JR (St52 Yapı Çeliği - 7.85 g/cm³)</option>
                            <option value="paslanmaz304">Paslanmaz Çelik AISI 304 (7.93 g/cm³)</option>
                            <option value="paslanmaz316">Paslanmaz Çelik AISI 316L (7.98 g/cm³)</option>
                            <option value="aluminyum">Alüminyum 5754 / 6061 (2.70 g/cm³)</option>
                            <option value="galvaniz">Galvaniz Sac DX51D (7.85 g/cm³)</option>
                            <option value="hardox450">Hardox 450 Aşınma Sacı (7.85 g/cm³)</option>
                        </select>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Sac Kalınlığı (mm)</label>
                            <select id="sacKalinlik" class="w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs font-semibold text-white outline-none font-mono">
                                <option value="1.0">1.0 mm</option>
                                <option value="1.5">1.5 mm</option>
                                <option value="2.0" selected>2.0 mm</option>
                                <option value="3.0">3.0 mm</option>
                                <option value="4.0">4.0 mm</option>
                                <option value="5.0">5.0 mm</option>
                                <option value="6.0">6.0 mm</option>
                                <option value="8.0">8.0 mm</option>
                                <option value="10.0">10.0 mm</option>
                                <option value="12.0">12.0 mm</option>
                                <option value="15.0">15.0 mm</option>
                                <option value="20.0">20.0 mm</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Sac Kg Fiyatı (TL/kg)</label>
                            <input type="number" id="sacKgFiyat" value="35.0" step="0.5" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-mono outline-none">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Kesim Hızı (m/dk)</label>
                            <input type="number" id="kesimHiz" value="4.50" step="0.1" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-emerald-400 font-mono outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Patlatma Süresi (sn)</label>
                            <input type="number" id="delmeSure" value="0.5" step="0.1" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-emerald-400 font-mono outline-none">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Fire Oranı (%)</label>
                            <input type="number" id="fireOrani" value="15" step="1" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-mono outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Tezgâh Saat Ücreti (TL)</label>
                            <input type="number" id="tezgahUcret" value="1800" step="50" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-mono outline-none">
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Kâr Marjı (%)</label>
                            <input type="number" id="karMarj" value="25" step="1" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-amber-400 font-bold font-mono outline-none">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">KDV Oranı (%)</label>
                            <input type="number" id="kdvOrani" value="20" step="1" class="live-param w-full bg-slate-950 border border-slate-700 focus:border-orange-500 rounded-lg px-3 py-2 text-xs text-white font-mono outline-none">
                        </div>
                    </div>

                    <input type="hidden" id="ozgulAgirlik" value="7.85">
                </div>
            </div>

            <!-- SAĞ PANEL: CAM ÖNİZLEME, MALİYET DAĞILIMI VE TEKLİF TABLOSU -->
            <div class="lg:col-span-8 space-y-5">

                <!-- 2D CNC CAM ÖNİZLEME & SEÇİLİ PARÇA ANALİZİ -->
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl">
                    <div class="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-slate-800">
                        <div class="flex items-center space-x-2">
                            <span class="text-xs font-extrabold uppercase tracking-wider text-slate-300">2D CNC Kesim Yolu Önizleme:</span>
                            <span id="activePartName" class="text-xs font-mono font-bold text-orange-400 bg-orange-500/10 px-2.5 py-0.5 rounded border border-orange-500/20">Parça Bekleniyor...</span>
                        </div>
                        <div class="flex items-center space-x-4 text-[11px] text-slate-400">
                            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-orange-500 inline-block"></span><span>Dış Kontur</span></span>
                            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block"></span><span>İç Boşaltma / Delik</span></span>
                            <span class="flex items-center space-x-1"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span><span>Patlatma (Pierce)</span></span>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
                        <div id="svgContainer" class="md:col-span-8 h-60 blueprint-grid rounded-xl border border-slate-800 p-4 flex items-center justify-center">
                            <p class="text-xs text-slate-500 font-mono">Sol panelden DXF dosyalarını sürükleyin veya seçin</p>
                        </div>
                        <div class="md:col-span-4 bg-slate-950 border border-slate-800/90 rounded-xl p-4 space-y-2.5 text-xs">
                            <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800 pb-1.5">Seçili Parça Birim Analizi</div>
                            <div class="flex justify-between"><span class="text-slate-400">Plaka Ebadı:</span><span id="detEbat" class="font-mono text-white">-</span></div>
                            <div class="flex justify-between"><span class="text-slate-400">Lazer Kesim Yolu:</span><span id="detKesim" class="font-mono text-orange-400">-</span></div>
                            <div class="flex justify-between"><span class="text-slate-400">Patlatma Sayısı:</span><span id="detDelik" class="font-mono text-emerald-400">-</span></div>
                            <div class="flex justify-between"><span class="text-slate-400">Birim Kesim Süresi:</span><span id="detSure" class="font-mono text-slate-200">-</span></div>
                            <div class="flex justify-between"><span class="text-slate-400">Brüt Ağırlık:</span><span id="detAgirlik" class="font-mono text-sky-400">-</span></div>
                            <div class="border-t border-slate-800 pt-2 space-y-1">
                                <div class="flex justify-between text-[11px]"><span class="text-slate-500">Sac Hammadde:</span><span id="detMalzemeTl" class="font-mono text-slate-300">-</span></div>
                                <div class="flex justify-between text-[11px]"><span class="text-slate-500">Lazer İşçilik:</span><span id="detIscilikTl" class="font-mono text-slate-300">-</span></div>
                                <div class="flex justify-between font-bold text-xs pt-1"><span class="text-orange-400">Birim Satış Fiyatı:</span><span id="detSatisTl" class="font-mono text-orange-400">-</span></div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- MALİYET DAĞILIM ÇUBUĞU -->
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl">
                    <div class="flex items-center justify-between text-xs mb-2">
                        <span class="font-bold text-slate-300 uppercase tracking-wider">Toplam Teklif Maliyet & Kâr Dağılımı</span>
                        <div class="flex space-x-4 text-[11px] font-mono">
                            <span id="barLabelMat" class="text-sky-400">Hammadde: %0</span>
                            <span id="barLabelLab" class="text-purple-400">Lazer İşçilik: %0</span>
                            <span id="barLabelProf" class="text-emerald-400">Net Kâr: %0</span>
                        </div>
                    </div>
                    <div class="w-full h-3 bg-slate-950 rounded-full overflow-hidden flex border border-slate-800">
                        <div id="barMat" class="bg-sky-500 h-full transition-all duration-300" style="width: 50%"></div>
                        <div id="barLab" class="bg-purple-500 h-full transition-all duration-300" style="width: 30%"></div>
                        <div id="barProf" class="bg-emerald-500 h-full transition-all duration-300" style="width: 20%"></div>
                    </div>
                </div>

                <!-- PARÇA LİSTESİ & TEKLİF TABLOSU -->
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl">
                    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                        <div class="flex items-center space-x-3">
                            <h3 class="text-sm font-extrabold text-white uppercase tracking-wider">Parça Listesi ve Adet Hesaplama</h3>
                            <button id="clearListBtn" type="button" class="text-[11px] text-slate-400 hover:text-rose-400 bg-slate-950 border border-slate-800 px-2.5 py-1 rounded-md transition">
                                Listeyi Temizle
                            </button>
                        </div>
                        <div class="flex flex-wrap gap-2">
                            <button id="csvBtn" type="button" class="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold py-2 px-3.5 rounded-lg border border-slate-700 transition">
                                📊 Excel (CSV) İndir
                            </button>
                            <button id="pdfBtn" type="button" class="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold py-2 px-4 rounded-lg shadow-lg shadow-emerald-600/20 transition">
                                📄 Resmi Kurumsal Teklif PDF İndir
                            </button>
                        </div>
                    </div>

                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="border-b border-slate-800 text-[11px] text-slate-400 uppercase">
                                    <th class="py-2.5 px-2">#</th>
                                    <th class="py-2.5 px-2">Parça / DXF Adı</th>
                                    <th class="py-2.5 px-2">Ebat (mm)</th>
                                    <th class="py-2.5 px-2">Kesim / Delik</th>
                                    <th class="py-2.5 px-2">Birim Kg</th>
                                    <th class="py-2.5 px-2 text-center">Üretim Adedi</th>
                                    <th class="py-2.5 px-2 text-right">Birim Fiyat</th>
                                    <th class="py-2.5 px-2 text-right">Satır Toplamı</th>
                                    <th class="py-2.5 px-1"></th>
                                </tr>
                            </thead>
                            <tbody id="partsTableBody" class="divide-y divide-slate-800/60 text-xs">
                                <tr>
                                    <td colspan="9" class="py-10 text-center text-slate-500">
                                        Henüz parça yüklenmedi. Sol paneldeki CAD / DXF Yükleme Merkezinden dosyalarınızı seçerek analizi başlatabilirsiniz.
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
        const MATERIAL_MATRIX = {
            dkp:          { name: "DKP / S235JR (St37) Sac", density: 7.85, price: 35.0,  speedFactor: 1.00, gas: "O2 (Oksijen)" },
            s355:         { name: "S355JR (St52) Yapı Çeliği", density: 7.85, price: 42.0, speedFactor: 0.90, gas: "O2 (Oksijen)" },
            paslanmaz304: { name: "Paslanmaz Çelik (AISI 304)", density: 7.93, price: 145.0, speedFactor: 0.75, gas: "N2 (Yüksek Basınç Azot)" },
            paslanmaz316: { name: "Paslanmaz Çelik (AISI 316L)", density: 7.98, price: 185.0, speedFactor: 0.70, gas: "N2 (Yüksek Basınç Azot)" },
            aluminyum:    { name: "Alüminyum (5754 / 6061)", density: 2.70, price: 160.0, speedFactor: 1.15, gas: "N2 (Azot)" },
            galvaniz:     { name: "Galvaniz Sac (DX51D)", density: 7.85, price: 40.0, speedFactor: 0.95, gas: "Hava / N2" },
            hardox450:    { name: "Hardox 450 Aşınma Sacı", density: 7.85, price: 95.0, speedFactor: 0.65, gas: "O2 (Oksijen)" }
        };

        const THICKNESS_PRESETS = {
            "1.0":  { speed: 8.5, pierce: 0.2 },
            "1.5":  { speed: 6.2, pierce: 0.3 },
            "2.0":  { speed: 4.5, pierce: 0.5 },
            "3.0":  { speed: 3.2, pierce: 0.8 },
            "4.0":  { speed: 2.5, pierce: 1.0 },
            "5.0":  { speed: 2.0, pierce: 1.2 },
            "6.0":  { speed: 1.6, pierce: 1.5 },
            "8.0":  { speed: 1.2, pierce: 2.0 },
            "10.0": { speed: 0.85, pierce: 2.8 },
            "12.0": { speed: 0.65, pierce: 3.5 },
            "15.0": { speed: 0.45, pierce: 4.5 },
            "20.0": { speed: 0.30, pierce: 6.0 }
        };

        let parcaListesi = [];
        let activeIndex = 0;

        const malzemeSelect = document.getElementById("malzemeTuru");
        const kalinlikSelect = document.getElementById("sacKalinlik");
        const kgFiyatInput = document.getElementById("sacKgFiyat");
        const kesimHizInput = document.getElementById("kesimHiz");
        const delmeSureInput = document.getElementById("delmeSure");
        const ozgulInput = document.getElementById("ozgulAgirlik");
        const gasBadge = document.getElementById("gasBadge");
        const fileInput = document.getElementById("dxfFiles");
        const dropzone = document.getElementById("dropzone");

        // 0ms İstemci Tarafı Canlı Mühendislik Hesaplaması
        function recalculateAllLive() {
            const kalinlik = parseFloat(kalinlikSelect.value) || 2.0;
            const ozgul = parseFloat(ozgulInput.value) || 7.85;
            const kgFiyat = parseFloat(kgFiyatInput.value) || 35.0;
            const kesimHiz = Math.max(parseFloat(kesimHizInput.value) || 4.5, 0.05);
            const delmeSure = parseFloat(delmeSureInput.value) || 0.5;
            const fireOrani = parseFloat(document.getElementById("fireOrani").value) || 15.0;
            const tezgahUcret = parseFloat(document.getElementById("tezgahUcret").value) || 1800.0;
            const karMarj = parseFloat(document.getElementById("karMarj").value) || 25.0;
            const kdvOrani = parseFloat(document.getElementById("kdvOrani").value) || 20.0;

            let topAgirlik = 0, topKesimM = 0, topDelik = 0, topSureSn = 0, topAdet = 0;
            let topMalzemeTl = 0, topIscilikTl = 0, topSatisTl = 0;

            parcaListesi.forEach(p => {
                const netKg = (p.genislik_mm * p.boy_mm * kalinlik) * (ozgul / 1000000.0);
                const brutKg = netKg * (1.0 + (fireOrani / 100.0));
                const malzemeTl = brutKg * kgFiyat;

                const sureDk = (p.kesim_metre / kesimHiz) + ((p.patlatma_adedi * delmeSure) / 60.0);
                const sureSn = sureDk * 60.0;
                const iscilikTl = (sureDk / 60.0) * tezgahUcret;

                const maliyetTl = malzemeTl + iscilikTl;
                const satisTl = maliyetTl * (1.0 + (karMarj / 100.0));

                p.birim_agirlik_kg = Number(brutKg.toFixed(3));
                p.birim_sure_sn = Number(sureSn.toFixed(1));
                p.birim_malzeme_tl = Number(malzemeTl.toFixed(2));
                p.birim_iscilik_tl = Number(iscilikTl.toFixed(2));
                p.birim_satis_tl = Number(satisTl.toFixed(2));

                topAdet += p.adet;
                topAgirlik += brutKg * p.adet;
                topKesimM += p.kesim_metre * p.adet;
                topDelik += p.patlatma_adedi * p.adet;
                topSureSn += sureSn * p.adet;
                topMalzemeTl += malzemeTl * p.adet;
                topIscilikTl += iscilikTl * p.adet;
                topSatisTl += satisTl * p.adet;
            });

            const netKarTl = topSatisTl - (topMalzemeTl + topIscilikTl);
            const genelToplamTl = topSatisTl * (1.0 + (kdvOrani / 100.0));

            document.getElementById("kpiKalem").innerText = `${parcaListesi.length} Kalem (${topAdet} Adet)`;
            document.getElementById("kpiKesim").innerText = `${topKesimM.toFixed(1)} m / ${topDelik} delik`;
            document.getElementById("kpiSure").innerText = `${(topSureSn / 60.0).toFixed(1)} dk`;
            document.getElementById("kpiAgirlik").innerText = `${topAgirlik.toFixed(2)} kg`;
            document.getElementById("kpiNetKar").innerText = `${netKarTl.toFixed(2)} TL`;
            document.getElementById("kpiGenelToplam").innerText = `${genelToplamTl.toFixed(2)} TL`;

            if (topSatisTl > 0) {
                const pMat = Math.round((topMalzemeTl / topSatisTl) * 100);
                const pLab = Math.round((topIscilikTl / topSatisTl) * 100);
                const pProf = Math.max(0, 100 - pMat - pLab);
                document.getElementById("barMat").style.width = pMat + "%";
                document.getElementById("barLab").style.width = pLab + "%";
                document.getElementById("barProf").style.width = pProf + "%";
                document.getElementById("barLabelMat").innerText = `Hammadde: %${pMat} (${topMalzemeTl.toFixed(0)} TL)`;
                document.getElementById("barLabelLab").innerText = `Lazer İşçilik: %${pLab} (${topIscilikTl.toFixed(0)} TL)`;
                document.getElementById("barLabelProf").innerText = `Net Kâr: %${pProf} (${netKarTl.toFixed(0)} TL)`;
            }

            renderTable();
            updatePreviewPanel(activeIndex);
        }

        function updateMatrixPresets() {
            const mat = MATERIAL_MATRIX[malzemeSelect.value];
            const thk = THICKNESS_PRESETS[kalinlikSelect.value] || { speed: 3.0, pierce: 1.0 };
            kgFiyatInput.value = mat.price;
            ozgulInput.value = mat.density;
            kesimHizInput.value = (thk.speed * mat.speedFactor).toFixed(2);
            delmeSureInput.value = thk.pierce.toFixed(1);
            gasBadge.innerText = "Gaz: " + mat.gas;
            recalculateAllLive();
        }

        malzemeSelect.addEventListener("change", updateMatrixPresets);
        kalinlikSelect.addEventListener("change", updateMatrixPresets);
        document.querySelectorAll(".live-param").forEach(inp => {
            inp.addEventListener("input", recalculateAllLive);
        });

        function updatePreviewPanel(idx) {
            if (!parcaListesi.length) {
                document.getElementById("activePartName").innerText = "Parça Bekleniyor...";
                document.getElementById("svgContainer").innerHTML = '<p class="text-xs text-slate-500 font-mono">Sol panelden DXF dosyalarını sürükleyin veya seçin</p>';
                return;
            }
            activeIndex = Math.min(Math.max(idx, 0), parcaListesi.length - 1);
            const p = parcaListesi[activeIndex];
            document.getElementById("activePartName").innerText = p.dosya_adi;
            document.getElementById("svgContainer").innerHTML = p.svg_cizim;
            document.getElementById("detEbat").innerText = p.ebat_metin;
            document.getElementById("detKesim").innerText = p.kesim_metre + " m";
            document.getElementById("detDelik").innerText = p.patlatma_adedi + " adet";
            document.getElementById("detSure").innerText = p.birim_sure_sn + " sn";
            document.getElementById("detAgirlik").innerText = p.birim_agirlik_kg + " kg";
            document.getElementById("detMalzemeTl").innerText = p.birim_malzeme_tl.toFixed(2) + " TL";
            document.getElementById("detIscilikTl").innerText = p.birim_iscilik_tl.toFixed(2) + " TL";
            document.getElementById("detSatisTl").innerText = p.birim_satis_tl.toFixed(2) + " TL";
        }

        function renderTable() {
            const tbody = document.getElementById("partsTableBody");
            if (!parcaListesi.length) {
                tbody.innerHTML = '<tr><td colspan="9" class="py-10 text-center text-slate-500">Liste boş. Analiz için sol panelden DXF dosyası yükleyin.</td></tr>';
                return;
            }
            tbody.innerHTML = "";
            parcaListesi.forEach((p, idx) => {
                const satirToplam = p.birim_satis_tl * p.adet;
                const isSelected = idx === activeIndex;
                const tr = document.createElement("tr");
                tr.className = `cursor-pointer transition ${isSelected ? 'bg-orange-500/10 border-l-2 border-l-orange-500' : 'hover:bg-slate-800/50'}`;
                tr.onclick = (e) => {
                    if (e.target.tagName !== "INPUT" && e.target.tagName !== "BUTTON") {
                        activeIndex = idx;
                        renderTable();
                        updatePreviewPanel(idx);
                    }
                };

                tr.innerHTML = `
                    <td class="py-2.5 px-2 font-mono text-slate-500">${idx + 1}</td>
                    <td class="py-2.5 px-2 font-semibold text-white">${p.dosya_adi}</td>
                    <td class="py-2.5 px-2 font-mono text-slate-300">${p.ebat_metin}</td>
                    <td class="py-2.5 px-2 font-mono text-slate-400">${p.kesim_metre}m / ${p.patlatma_adedi}d</td>
                    <td class="py-2.5 px-2 font-mono text-sky-400">${p.birim_agirlik_kg} kg</td>
                    <td class="py-2.5 px-2">
                        <div class="flex items-center justify-center space-x-1">
                            <button type="button" data-act="dec" data-idx="${idx}" class="qty-btn w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold">-</button>
                            <input type="number" min="1" value="${p.adet}" data-idx="${idx}" class="qty-input w-14 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-white font-mono text-center">
                            <button type="button" data-act="inc" data-idx="${idx}" class="qty-btn w-6 h-6 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold">+</button>
                        </div>
                    </td>
                    <td class="py-2.5 px-2 font-mono text-right text-slate-200">${p.birim_satis_tl.toFixed(2)} TL</td>
                    <td class="py-2.5 px-2 font-mono text-right font-bold text-orange-400">${satirToplam.toFixed(2)} TL</td>
                    <td class="py-2.5 px-1 text-right">
                        <button type="button" data-del="${idx}" class="del-btn text-slate-500 hover:text-rose-400 px-1.5 font-bold">✕</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            document.querySelectorAll(".qty-btn").forEach(btn => {
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const i = parseInt(btn.getAttribute("data-idx"));
                    const act = btn.getAttribute("data-act");
                    if (act === "inc") parcaListesi[i].adet += 1;
                    else parcaListesi[i].adet = Math.max(1, parcaListesi[i].adet - 1);
                    recalculateAllLive();
                };
            });

            document.querySelectorAll(".qty-input").forEach(inp => {
                inp.onchange = (e) => {
                    const i = parseInt(inp.getAttribute("data-idx"));
                    parcaListesi[i].adet = Math.max(1, parseInt(inp.value) || 1);
                    recalculateAllLive();
                };
            });

            document.querySelectorAll(".del-btn").forEach(btn => {
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const i = parseInt(btn.getAttribute("data-del"));
                    parcaListesi.splice(i, 1);
                    recalculateAllLive();
                };
            });
        }

        async function uploadFilesToEngine(files) {
            if (!files || files.length === 0) return;
            const fd = new FormData();
            let validCount = 0;
            for (let i = 0; i < files.length; i++) {
                if (files[i].name.toLowerCase().endsWith(".dxf")) {
                    fd.append("files", files[i]);
                    validCount++;
                }
            }
            if (validCount === 0) {
                alert("Lütfen .dxf uzantılı CAD dosyası seçin!");
                return;
            }
            const res = await fetch("/api/dxf-analiz", { method: "POST", body: fd });
            const data = await res.json();
            if (res.ok) {
                const append = document.getElementById("appendMode").checked;
                if (append && parcaListesi.length > 0) {
                    parcaListesi = parcaListesi.concat(data.parcalar);
                } else {
                    parcaListesi = data.parcalar;
                    activeIndex = 0;
                }
                recalculateAllLive();
            } else {
                alert("Hata: " + (data.detail || "DXF okunamadı"));
            }
        }

        fileInput.addEventListener("change", (e) => {
            uploadFilesToEngine(e.target.files);
            fileInput.value = "";
        });

        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.classList.add("border-orange-500", "bg-slate-900");
        });
        dropzone.addEventListener("dragleave", () => {
            dropzone.classList.remove("border-orange-500", "bg-slate-900");
        });
        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.classList.remove("border-orange-500", "bg-slate-900");
            if (e.dataTransfer && e.dataTransfer.files.length > 0) {
                uploadFilesToEngine(e.dataTransfer.files);
            }
        });

        async function loadDemo10Parts() {
            const res = await fetch("/api/ornek-10-parca");
            const data = await res.json();
            if (res.ok) {
                parcaListesi = data.parcalar;
                activeIndex = 0;
                recalculateAllLive();
            }
        }

        
        document.getElementById("clearListBtn").onclick = () => {
            parcaListesi = [];
            recalculateAllLive();
        };

        document.getElementById("pdfBtn").onclick = async () => {
            if (!parcaListesi.length) {
                alert("Önce parça yükleyin!");
                return;
            }
            const mat = MATERIAL_MATRIX[malzemeSelect.value];
            const payload = {
                atolye_adi: document.getElementById("atolyeAdi").value,
                musteri_adi: document.getElementById("musteriAdi").value,
                teklif_notu: document.getElementById("teklifNotu").value,
                malzeme_adi: mat.name,
                kalinlik_mm: parseFloat(kalinlikSelect.value),
                kesim_gazi: mat.gas,
                kdv_orani: parseFloat(document.getElementById("kdvOrani").value) || 20.0,
                kalemler: parcaListesi
            };
            const res = await fetch("/api/kurumsal-pdf-indir", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                const blob = await res.blob();
                const a = document.createElement("a");
                a.href = window.URL.createObjectURL(blob);
                a.download = "Sariguzel_Teklif_Resmi_Form.pdf";
                a.click();
            }
        };

        document.getElementById("csvBtn").onclick = () => {
            if (!parcaListesi.length) return;
            const rows = ["\uFEFFParca Adi;Ebat (mm);Kesim Metresi (m);Patlatma Adedi;Birim Agirlik (kg);Birim Sure (sn);Adet;Birim Satis (TL);Toplam Tutar (TL)"];
            parcaListesi.forEach(p => {
                rows.append ? null : null;
                rows.push(`${p.dosya_adi};${p.ebat_metin};${p.kesim_metre};${p.patlatma_adedi};${p.birim_agirlik_kg};${p.birim_sure_sn};${p.adet};${p.birim_satis_tl};${(p.birim_satis_tl * p.adet).toFixed(2)}`);
            });
            const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "Sariguzel_Teklif_Tablosu.csv";
            a.click();
        };

        // Sayfa açıldığında 10 endüstriyel parçayı otomatik hazır getir
        window.addEventListener("DOMContentLoaded", () => {
            // Otomatik demo yükleme kapalı
        });
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return HTMLResponse(content=HTML_PAGE)
