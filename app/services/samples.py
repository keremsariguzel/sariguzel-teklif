import math
import os

import ezdxf

from app.core.config import SAMPLE_DIR


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
