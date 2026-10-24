import math
import tempfile
import unittest
from pathlib import Path

import ezdxf

from app.services.dxf import parse_dxf_geometry


class ParseDxfGeometryTests(unittest.TestCase):
    def analyze_document(self, document, filename="part.dxf"):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "part.dxf"
            document.saveas(file_path)
            return parse_dxf_geometry(str(file_path), filename)

    def test_bulge_polyline_uses_arc_length_and_bounds(self):
        document = ezdxf.new()
        document.modelspace().add_lwpolyline(
            [(0, 0, 1), (20, 0, 0)],
            format="xyb",
        )

        result = self.analyze_document(document)

        self.assertAlmostEqual(result["kesim_metre"], round(math.pi * 10 / 1000, 3))
        self.assertAlmostEqual(result["boy_mm"], 10.0, places=1)
        self.assertEqual(result["patlatma_adedi"], 1)

    def test_arc_bounds_include_cardinal_extrema(self):
        document = ezdxf.new()
        document.modelspace().add_arc(
            center=(0, 0),
            radius=10,
            start_angle=0,
            end_angle=90,
        )

        result = self.analyze_document(document)

        self.assertEqual(result["genislik_mm"], 10.0)
        self.assertEqual(result["boy_mm"], 10.0)
        self.assertAlmostEqual(result["kesim_metre"], round(math.pi * 5 / 1000, 3))

    def test_closed_ellipse_is_one_contour(self):
        document = ezdxf.new()
        document.modelspace().add_ellipse(
            center=(0, 0),
            major_axis=(10, 0),
            ratio=0.5,
        )

        result = self.analyze_document(document)

        self.assertEqual(result["genislik_mm"], 20.0)
        self.assertEqual(result["boy_mm"], 10.0)
        self.assertEqual(result["patlatma_adedi"], 1)
        self.assertGreater(result["kesim_metre"], 0)

    def test_unsupported_cut_geometry_is_reported(self):
        document = ezdxf.new()
        document.modelspace().add_3dface(
            [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
        )

        with self.assertRaisesRegex(ValueError, "3DFACE"):
            self.analyze_document(document)

    def test_filename_is_reduced_to_its_basename(self):
        document = ezdxf.new()
        document.modelspace().add_circle((0, 0), radius=5)

        result = self.analyze_document(document, r"..\folder\part.dxf")

        self.assertEqual(result["dosya_adi"], "part.dxf")


if __name__ == "__main__":
    unittest.main()
