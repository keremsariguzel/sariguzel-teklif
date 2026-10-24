import math
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import ezdxf
import networkx as nx
from ezdxf.path import make_path


Point = Tuple[float, float]
IGNORED_ENTITY_TYPES = {
    "ATTDEF",
    "ATTRIB",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "POINT",
    "TEXT",
    "MTEXT",
    "VIEWPORT",
    "XLINE",
    "RAY",
    "IMAGE",
    "WIPEOUT",
}
SUPPORTED_ENTITY_TYPES = {
    "LINE",
    "CIRCLE",
    "ARC",
    "LWPOLYLINE",
    "POLYLINE",
    "ELLIPSE",
    "SPLINE",
    "INSERT",
}


def _point_key(point: Point) -> Point:
    return round(point[0], 2), round(point[1], 2)


def _distance(start: Point, end: Point) -> float:
    return math.hypot(end[0] - start[0], end[1] - start[1])


def _sample_bulge(
    start: Point, end: Point, bulge: float
) -> Tuple[List[Point], float, List[Point]]:
    chord = _distance(start, end)
    if chord == 0:
        return [start], 0.0, [start]
    if abs(bulge) < 1e-12:
        return [start, end], chord, [start, end]

    sweep = 4.0 * math.atan(bulge)
    radius = chord * (1.0 + bulge * bulge) / (4.0 * abs(bulge))
    midpoint_x = (start[0] + end[0]) / 2.0
    midpoint_y = (start[1] + end[1]) / 2.0
    offset = chord * (1.0 - bulge * bulge) / (4.0 * bulge)
    center_x = midpoint_x - (end[1] - start[1]) / chord * offset
    center_y = midpoint_y + (end[0] - start[0]) / chord * offset
    start_angle = math.atan2(start[1] - center_y, start[0] - center_x)
    segments = max(2, math.ceil(abs(sweep) / math.radians(5)))
    points = [
        (
            center_x + radius * math.cos(start_angle + sweep * index / segments),
            center_y + radius * math.sin(start_angle + sweep * index / segments),
        )
        for index in range(segments + 1)
    ]
    points[0] = start
    points[-1] = end
    curve_bounds = _arc_bounds(
        (center_x, center_y),
        radius,
        start_angle,
        sweep,
    )
    return points, radius * abs(sweep), curve_bounds


def _polyline_vertices(entity) -> List[Tuple[float, float, float]]:
    if entity.dxftype() == "LWPOLYLINE":
        return [
            (point[0], point[1], point[2] if len(point) > 2 else 0.0)
            for point in entity.get_points("xyb")
        ]
    return [
        (
            vertex.dxf.location.x,
            vertex.dxf.location.y,
            vertex.dxf.get("bulge", 0.0),
        )
        for vertex in entity.vertices
    ]


def _polyline_segments(entity) -> Iterable[Tuple[Point, Point, float]]:
    vertices = _polyline_vertices(entity)
    if len(vertices) < 2:
        return
    segment_count = len(vertices) if entity.is_closed else len(vertices) - 1
    for index in range(segment_count):
        first = vertices[index]
        second = vertices[(index + 1) % len(vertices)]
        yield (first[0], first[1]), (second[0], second[1]), first[2]


def _arc_bounds(center: Point, radius: float, start_angle: float, sweep: float) -> List[Point]:
    angles = [start_angle, start_angle + sweep]
    for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
        delta = (angle - start_angle) % (2.0 * math.pi)
        if sweep >= 0 and delta <= sweep:
            angles.append(angle)
        elif sweep < 0 and ((start_angle - angle) % (2.0 * math.pi)) <= -sweep:
            angles.append(angle)
    return [
        (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
        for angle in angles
    ]


def parse_dxf_geometry(file_path: str, filename: str) -> dict:
    try:
        document = ezdxf.readfile(file_path)
    except (OSError, ezdxf.DXFError) as error:
        raise ValueError("Dosya geçerli veya okunabilir bir DXF dosyası değil.") from error

    modelspace = document.modelspace()
    total_cut_length = 0.0
    bounds: List[Point] = []
    svg_elements: List[str] = []
    graph = nx.Graph()
    circle_count = 0
    circle_markers: List[Point] = []
    unsupported = set()

    def add_polyline(points: Sequence[Point], closed: bool) -> None:
        if len(points) < 2:
            return
        coords = " ".join(f"{x:.2f},{-y:.2f}" for x, y in points)
        tag = "polygon" if closed else "polyline"
        fill = "#f97316" if closed else "none"
        fill_opacity = ' fill-opacity="0.05"' if closed else ""
        svg_elements.append(
            f'<{tag} points="{coords}" fill="{fill}"{fill_opacity} stroke="#f97316" '
            'stroke-width="2.2" vector-effect="non-scaling-stroke" />'
        )
        for point in points:
            bounds.append(point)
        edges = zip(points, points[1:])
        for start, end in edges:
            graph.add_edge(_point_key(start), _point_key(end))
        if closed:
            graph.add_edge(_point_key(points[-1]), _point_key(points[0]))

    def process_entity(entity) -> None:
        nonlocal total_cut_length, circle_count
        entity_type = entity.dxftype()

        if entity_type == "INSERT":
            try:
                for virtual_entity in entity.virtual_entities():
                    process_entity(virtual_entity)
            except (AttributeError, ezdxf.DXFError, ValueError) as error:
                raise ValueError("DXF içindeki blok geometrisi çözümlenemedi.") from error
            return

        if entity_type in IGNORED_ENTITY_TYPES:
            return
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            unsupported.add(entity_type)
            return

        if entity_type == "LINE":
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            total_cut_length += _distance(start, end)
            bounds.extend((start, end))
            graph.add_edge(_point_key(start), _point_key(end))
            svg_elements.append(
                f'<line x1="{start[0]:.2f}" y1="{-start[1]:.2f}" '
                f'x2="{end[0]:.2f}" y2="{-end[1]:.2f}" stroke="#f97316" '
                'stroke-width="2" vector-effect="non-scaling-stroke" />'
            )
            return

        if entity_type == "CIRCLE":
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            if radius <= 0:
                raise ValueError("DXF içinde yarıçapı sıfır veya negatif bir daire var.")
            total_cut_length += 2.0 * math.pi * radius
            circle_count += 1
            circle_markers.append((center[0] + radius, -center[1]))
            bounds.extend(
                (
                    (center[0] - radius, center[1] - radius),
                    (center[0] + radius, center[1] + radius),
                )
            )
            svg_elements.append(
                f'<circle cx="{center[0]:.2f}" cy="{-center[1]:.2f}" r="{radius:.2f}" '
                'fill="#38bdf8" fill-opacity="0.06" stroke="#38bdf8" '
                'stroke-width="1.8" vector-effect="non-scaling-stroke" />'
            )
            return

        if entity_type == "ARC":
            center = (entity.dxf.center.x, entity.dxf.center.y)
            radius = entity.dxf.radius
            start_angle = math.radians(entity.dxf.start_angle)
            sweep = math.radians((entity.dxf.end_angle - entity.dxf.start_angle) % 360.0)
            if radius <= 0 or sweep <= 0:
                raise ValueError("DXF içinde geçersiz bir yay var.")
            start = (
                center[0] + radius * math.cos(start_angle),
                center[1] + radius * math.sin(start_angle),
            )
            end_angle = start_angle + sweep
            end = (
                center[0] + radius * math.cos(end_angle),
                center[1] + radius * math.sin(end_angle),
            )
            bounds.extend(_arc_bounds(center, radius, start_angle, sweep))
            total_cut_length += radius * sweep
            graph.add_edge(_point_key(start), _point_key(end))
            svg_elements.append(
                f'<path d="M {start[0]:.2f} {-start[1]:.2f} '
                f'A {radius:.2f} {radius:.2f} 0 {int(sweep > math.pi)} 0 '
                f'{end[0]:.2f} {-end[1]:.2f}" fill="none" stroke="#f97316" '
                'stroke-width="2" vector-effect="non-scaling-stroke" />'
            )
            return

        if entity_type in ("LWPOLYLINE", "POLYLINE"):
            vertices = _polyline_vertices(entity)
            sampled_points: List[Point] = []
            segments = list(_polyline_segments(entity))
            for start, end, bulge in segments:
                segment_points, segment_length, segment_bounds = _sample_bulge(
                    start, end, bulge
                )
                total_cut_length += segment_length
                bounds.extend(segment_bounds)
                if sampled_points:
                    sampled_points.extend(segment_points[1:])
                else:
                    sampled_points.extend(segment_points)
            if not entity.is_closed and not segments:
                sampled_points = [(point[0], point[1]) for point in vertices]
            add_polyline(sampled_points, entity.is_closed)
            return

        try:
            path = make_path(entity)
            points = [(point.x, point.y) for point in path.flattening(0.1, segments=8)]
        except (AttributeError, TypeError, ValueError, ezdxf.DXFError) as error:
            raise ValueError(f"{entity_type} geometrisi çözümlenemedi.") from error
        if len(points) < 2:
            raise ValueError(f"{entity_type} geometrisi boş veya geçersiz.")
        total_cut_length += sum(_distance(a, b) for a, b in zip(points, points[1:]))
        closed = bool(getattr(entity, "closed", False))
        if entity_type == "ELLIPSE":
            parameter_span = abs(entity.dxf.end_param - entity.dxf.start_param)
            closed = math.isclose(parameter_span, 2.0 * math.pi, rel_tol=0.0, abs_tol=1e-6)
        if closed and _distance(points[0], points[-1]) > 1e-6:
            total_cut_length += _distance(points[-1], points[0])
        add_polyline(points, closed)

    for item in modelspace:
        process_entity(item)

    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise ValueError(f"Desteklenmeyen DXF geometrisi bulundu: {names}.")
    if not bounds or total_cut_length <= 0:
        raise ValueError("DXF içinde analiz edilebilir kesim geometrisi bulunamadı.")

    min_x = min(point[0] for point in bounds)
    max_x = max(point[0] for point in bounds)
    min_y = min(point[1] for point in bounds)
    max_y = max(point[1] for point in bounds)
    width = max(max_x - min_x, 0.1)
    height = max(max_y - min_y, 0.1)
    pad = max(width, height) * 0.10 + 4.0
    view_box = (
        min_x - pad,
        -max_y - pad,
        max(width + 2.0 * pad, 1.0),
        max(height + 2.0 * pad, 1.0),
    )

    pierce_markers = circle_markers + [
        (point[0], -point[1])
        for component in nx.connected_components(graph)
        for point in [min(component)]
    ]
    pierce_count = circle_count + nx.number_connected_components(graph)
    if pierce_count == 0:
        pierce_count = circle_count

    marker_radius = max(width, height) * 0.014
    dots_svg = "".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{marker_radius:.2f}" fill="#10b981" />'
        for x, y in pierce_markers[:60]
    )
    svg = (
        f'<svg viewBox="{view_box[0]:.2f} {view_box[1]:.2f} '
        f'{view_box[2]:.2f} {view_box[3]:.2f}" xmlns="http://www.w3.org/2000/svg" '
        'class="w-full h-full max-h-60">'
        + "".join(svg_elements)
        + dots_svg
        + "</svg>"
    )

    return {
        "dosya_adi": Path(filename.replace("\\", "/")).name,
        "genislik_mm": round(width, 1),
        "boy_mm": round(height, 1),
        "ebat_metin": f"{width:.1f} x {height:.1f} mm",
        "kesim_metre": round(total_cut_length / 1000.0, 3),
        "patlatma_adedi": max(pierce_count, 1),
        "adet": 1,
        "svg_cizim": svg,
    }
