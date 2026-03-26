import importlib.util
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "docs" / "images"


def load_module(name, relative_path):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dp2d = load_module("double_pendulum_2d", "double_pendulum.py")
dp3d = load_module("double_pendulum_3d", "double_pendulum_3d.py")
dpp = load_module("double_pendulum_poincare", "double_pendulum_poincare.py")


def ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)


def svg_header(width, height, background):
    return [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        f"<rect width=\"100%\" height=\"100%\" fill=\"{background}\"/>",
        "<style>",
        "text{font-family:'Segoe UI','Yu Gothic UI',sans-serif}",
        ".mono{font-family:Consolas,'Courier New',monospace}",
        "</style>",
    ]


def svg_footer():
    return ["</svg>"]


def write_svg(path, parts):
    path.write_text("\n".join(parts), encoding="utf-8")


def sample_points(points, max_points):
    if len(points) <= max_points:
        return points
    indices = np.linspace(0, len(points) - 1, max_points, dtype=int)
    return points[indices]


def polyline_points(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def map_2d_points(points, width, height, padding):
    extent = float(np.max(np.abs(points))) + 0.25
    usable_width = width - padding * 2
    usable_height = height - padding * 2
    scale = min(usable_width, usable_height) / (2.0 * extent)
    center_x = width / 2.0
    center_y = height / 2.0
    mapped = np.empty_like(points)
    mapped[:, 0] = center_x + points[:, 0] * scale
    mapped[:, 1] = center_y - points[:, 1] * scale
    return mapped


def generate_2d_svg():
    width = 960
    height = 760
    padding = 70
    x1, y1, x2, y2 = dp2d.simulate(theta1_deg=120.0, theta2_deg=-10.0, duration=60.0, dt=0.01)
    trace = np.column_stack([x2, y2])
    mapped_trace = map_2d_points(sample_points(trace, 2200), width, height, padding)
    mapped_rods = map_2d_points(
        np.array([[0.0, 0.0], [x1[-1], y1[-1]], [x2[-1], y2[-1]]], dtype=float),
        width,
        height,
        padding,
    )
    reach = float(np.max(np.abs(np.concatenate([x1, y1, x2, y2])))) + 0.25
    mapped_axes = map_2d_points(
        np.array([[-reach, 0.0], [reach, 0.0], [0.0, -reach], [0.0, reach]], dtype=float),
        width,
        height,
        padding,
    )

    parts = svg_header(width, height, "#ffffff")
    parts.extend(
        [
            "<text x=\"28\" y=\"38\" font-size=\"24\" font-weight=\"700\" fill=\"#111827\">2D Double Pendulum</text>",
            "<text x=\"28\" y=\"62\" font-size=\"12\" fill=\"#4b5563\">Chaotic trajectory with adaptive playback-friendly sampling</text>",
            f"<line x1=\"{mapped_axes[0,0]:.2f}\" y1=\"{mapped_axes[0,1]:.2f}\" x2=\"{mapped_axes[1,0]:.2f}\" y2=\"{mapped_axes[1,1]:.2f}\" stroke=\"#e5e7eb\" stroke-width=\"2\"/>",
            f"<line x1=\"{mapped_axes[2,0]:.2f}\" y1=\"{mapped_axes[2,1]:.2f}\" x2=\"{mapped_axes[3,0]:.2f}\" y2=\"{mapped_axes[3,1]:.2f}\" stroke=\"#e5e7eb\" stroke-width=\"2\"/>",
            f"<polyline points=\"{polyline_points(mapped_trace)}\" fill=\"none\" stroke=\"#dc2626\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" opacity=\"0.9\"/>",
            f"<polyline points=\"{polyline_points(mapped_rods)}\" fill=\"none\" stroke=\"#2563eb\" stroke-width=\"5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>",
            f"<circle cx=\"{mapped_rods[0,0]:.2f}\" cy=\"{mapped_rods[0,1]:.2f}\" r=\"7\" fill=\"#111827\"/>",
            f"<circle cx=\"{mapped_rods[1,0]:.2f}\" cy=\"{mapped_rods[1,1]:.2f}\" r=\"12\" fill=\"#f97316\"/>",
            f"<circle cx=\"{mapped_rods[2,0]:.2f}\" cy=\"{mapped_rods[2,1]:.2f}\" r=\"12\" fill=\"#dc2626\"/>",
        ]
    )
    parts.extend(svg_footer())
    write_svg(IMAGES_DIR / "pendulum_2d.svg", parts)


def project_3d_points(points, width, height, azimuth, elevation, zoom):
    all_points = np.vstack([np.zeros((1, 3)), points])
    limit = float(np.max(np.abs(all_points))) + 0.25
    camera_distance = max(4.0 * limit, 4.0)
    focal = min(width, height) * 0.42 * zoom
    coords = []
    for point in points:
        rotated = dp3d.rotate_point(point, azimuth, elevation)
        depth = rotated[2] + camera_distance
        scale = focal / max(depth, 0.2)
        sx = width / 2.0 + rotated[0] * scale
        sy = height / 2.0 + rotated[1] * scale
        coords.append((sx, sy))
    return np.array(coords, dtype=float), limit


def generate_3d_svg():
    width = 1040
    height = 760
    azimuth = math.radians(42.0)
    elevation = math.radians(24.0)
    r1_history, r2_history = dp3d.simulate(duration=18.0, dt=0.01)
    trace1, limit = project_3d_points(sample_points(r1_history, 1800), width, height, azimuth, elevation, 1.0)
    trace2, _ = project_3d_points(sample_points(r2_history, 1800), width, height, azimuth, elevation, 1.0)
    rods, _ = project_3d_points(
        np.array([[0.0, 0.0, 0.0], r1_history[-1], r2_history[-1]], dtype=float),
        width,
        height,
        azimuth,
        elevation,
        1.0,
    )
    axis_length = limit * 1.2
    axes_world = np.array(
        [
            [0.0, 0.0, 0.0],
            [axis_length, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, axis_length, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, axis_length],
        ],
        dtype=float,
    )
    axes, _ = project_3d_points(axes_world, width, height, azimuth, elevation, 1.0)

    parts = svg_header(width, height, "#f8fafc")
    parts.extend(
        [
            "<text x=\"28\" y=\"38\" font-size=\"24\" font-weight=\"700\" fill=\"#111827\">3D Double Pendulum</text>",
            "<text x=\"28\" y=\"62\" font-size=\"12\" fill=\"#475569\">Free-direction constrained motion with mouse-rotatable camera in the app</text>",
            f"<line x1=\"{axes[0,0]:.2f}\" y1=\"{axes[0,1]:.2f}\" x2=\"{axes[1,0]:.2f}\" y2=\"{axes[1,1]:.2f}\" stroke=\"#ef4444\" stroke-width=\"3\"/>",
            f"<line x1=\"{axes[2,0]:.2f}\" y1=\"{axes[2,1]:.2f}\" x2=\"{axes[3,0]:.2f}\" y2=\"{axes[3,1]:.2f}\" stroke=\"#10b981\" stroke-width=\"3\"/>",
            f"<line x1=\"{axes[4,0]:.2f}\" y1=\"{axes[4,1]:.2f}\" x2=\"{axes[5,0]:.2f}\" y2=\"{axes[5,1]:.2f}\" stroke=\"#3b82f6\" stroke-width=\"3\"/>",
            f"<polyline points=\"{polyline_points(trace1)}\" fill=\"none\" stroke=\"#f59e0b\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" opacity=\"0.85\"/>",
            f"<polyline points=\"{polyline_points(trace2)}\" fill=\"none\" stroke=\"#16a34a\" stroke-width=\"2.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" opacity=\"0.85\"/>",
            f"<polyline points=\"{polyline_points(rods)}\" fill=\"none\" stroke=\"#1d4ed8\" stroke-width=\"5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/>",
            f"<circle cx=\"{rods[0,0]:.2f}\" cy=\"{rods[0,1]:.2f}\" r=\"7\" fill=\"#111827\"/>",
            f"<circle cx=\"{rods[1,0]:.2f}\" cy=\"{rods[1,1]:.2f}\" r=\"12\" fill=\"#f97316\"/>",
            f"<circle cx=\"{rods[2,0]:.2f}\" cy=\"{rods[2,1]:.2f}\" r=\"12\" fill=\"#dc2626\"/>",
        ]
    )
    parts.extend(svg_footer())
    write_svg(IMAGES_DIR / "pendulum_3d.svg", parts)


def panel_layout(points, rect, y_limit):
    x0, y0, x1, y1 = rect
    margin_left = 54
    margin_right = 24
    margin_top = 68
    margin_bottom = 48
    plot_x0 = x0 + margin_left
    plot_y0 = y0 + margin_top
    plot_x1 = x1 - margin_right
    plot_y1 = y1 - margin_bottom

    mapped = []
    for theta1, omega1 in points:
        px = plot_x0 + (theta1 + math.pi) / (2.0 * math.pi) * (plot_x1 - plot_x0)
        py = plot_y0 + (y_limit - omega1) / (2.0 * y_limit) * (plot_y1 - plot_y0)
        if plot_x0 <= px <= plot_x1 and plot_y0 <= py <= plot_y1:
            mapped.append((px, py))
    return mapped, (plot_x0, plot_y0, plot_x1, plot_y1)


def generate_poincare_svg():
    width = 1280
    height = 760
    regular_points, chaotic_points = dpp.compute_poincare_datasets(
        duration=500.0,
        dt=0.01,
        m1=1.1,
        m2=1.0,
        l1=1.0,
        l2=1.0,
        regular_theta1=25.0,
        regular_theta2=5.0,
        chaotic_theta1=120.0,
        chaotic_theta2=-10.0,
    )
    combined = []
    if len(regular_points):
        combined.append(np.abs(regular_points[:, 1]))
    if len(chaotic_points):
        combined.append(np.abs(chaotic_points[:, 1]))
    y_limit = 1.0 if not combined else max(1.0, float(np.max(np.concatenate(combined))) * 1.1)

    left_panel = (40, 110, width / 2 - 20, height - 40)
    right_panel = (width / 2 + 20, 110, width - 40, height - 40)
    mapped_regular, regular_rect = panel_layout(regular_points, left_panel, y_limit)
    mapped_chaotic, chaotic_rect = panel_layout(chaotic_points, right_panel, y_limit)

    parts = svg_header(width, height, "#e2e8f0")
    parts.extend(
        [
            "<text x=\"28\" y=\"38\" font-size=\"24\" font-weight=\"700\" fill=\"#111827\">Poincare Sections</text>",
            "<text x=\"28\" y=\"62\" font-size=\"12\" fill=\"#475569\">Closed bands suggest regular motion. Spread-out clouds suggest stronger chaos.</text>",
        ]
    )

    for rect, title, subtitle, color, points in [
        (left_panel, "Regular-like initial condition", "theta1=25 deg, theta2=5 deg", "#2563eb", mapped_regular),
        (right_panel, "Chaotic-like initial condition", "theta1=120 deg, theta2=-10 deg", "#dc2626", mapped_chaotic),
    ]:
        x0, y0, x1, y1 = rect
        plot_x0, plot_y0, plot_x1, plot_y1 = regular_rect if rect == left_panel else chaotic_rect
        zero_x = plot_x0 + (-(-math.pi)) / (2.0 * math.pi) * (plot_x1 - plot_x0)
        zero_y = plot_y0 + (y_limit - 0.0) / (2.0 * y_limit) * (plot_y1 - plot_y0)
        parts.extend(
            [
                f"<rect x=\"{x0}\" y=\"{y0}\" width=\"{x1 - x0}\" height=\"{y1 - y0}\" fill=\"#ffffff\" stroke=\"#cbd5e1\"/>",
                f"<text x=\"{x0 + 18}\" y=\"{y0 + 28}\" font-size=\"18\" font-weight=\"700\" fill=\"#0f172a\">{title}</text>",
                f"<text x=\"{x0 + 18}\" y=\"{y0 + 52}\" font-size=\"11\" fill=\"#475569\">{subtitle}</text>",
                f"<rect x=\"{plot_x0}\" y=\"{plot_y0}\" width=\"{plot_x1 - plot_x0}\" height=\"{plot_y1 - plot_y0}\" fill=\"#f8fafc\" stroke=\"#cbd5e1\"/>",
                f"<line x1=\"{plot_x0}\" y1=\"{zero_y:.2f}\" x2=\"{plot_x1}\" y2=\"{zero_y:.2f}\" stroke=\"#cbd5e1\"/>",
                f"<line x1=\"{zero_x:.2f}\" y1=\"{plot_y0}\" x2=\"{zero_x:.2f}\" y2=\"{plot_y1}\" stroke=\"#cbd5e1\"/>",
            ]
        )
        for px, py in sample_points(np.asarray(points, dtype=float), 3200):
            parts.append(f"<circle cx=\"{px:.2f}\" cy=\"{py:.2f}\" r=\"1.5\" fill=\"{color}\"/>")

    parts.extend(svg_footer())
    write_svg(IMAGES_DIR / "poincare_sections.svg", parts)


def main():
    ensure_dir(IMAGES_DIR)
    generate_2d_svg()
    generate_3d_svg()
    generate_poincare_svg()
    print("Generated docs images in", IMAGES_DIR)


if __name__ == "__main__":
    main()
