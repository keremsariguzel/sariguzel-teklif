import io
import os
from datetime import datetime

from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont

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
        except (OSError, TTFError):
            pass

def tr_safe(text: str) -> str:
    if FONT_REG == "DejaVu":
        return str(text)
    tr_map = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    return str(text).translate(tr_map)


from app.schemas.quotes import BatchPDFRequest

def generate_corporate_pdf(req: BatchPDFRequest):
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

    if y < 270:
        p.showPage()
        y = height - 60

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
