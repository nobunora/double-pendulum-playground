import argparse
import math
import tkinter as tk

import numpy as np


def unit_vector_from_angles(azimuth_deg, elevation_deg):
    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    cos_elevation = math.cos(elevation)
    return np.array(
        [
            cos_elevation * math.cos(azimuth),
            cos_elevation * math.sin(azimuth),
            math.sin(elevation),
        ],
        dtype=float,
    )


def initial_state(
    l1,
    l2,
    azimuth1_deg,
    elevation1_deg,
    azimuth2_deg,
    elevation2_deg,
    omega1_vec,
    omega2_vec,
):
    r1 = l1 * unit_vector_from_angles(azimuth1_deg, elevation1_deg)
    d2 = l2 * unit_vector_from_angles(azimuth2_deg, elevation2_deg)
    r2 = r1 + d2

    omega1_vec = np.asarray(omega1_vec, dtype=float)
    omega2_vec = np.asarray(omega2_vec, dtype=float)

    v1 = np.cross(omega1_vec, r1)
    v2 = v1 + np.cross(omega2_vec, d2)
    return r1, r2, v1, v2


def project_positions(r1, r2, l1, l2):
    norm_r1 = np.linalg.norm(r1)
    if norm_r1 < 1e-12:
        r1 = np.array([0.0, 0.0, -l1], dtype=float)
    else:
        r1 = r1 * (l1 / norm_r1)

    d = r2 - r1
    norm_d = np.linalg.norm(d)
    if norm_d < 1e-12:
        d = np.array([l2, 0.0, 0.0], dtype=float)
    else:
        d = d * (l2 / norm_d)

    r2 = r1 + d
    return r1, r2


def project_velocities(r1, r2, v1, v2, m1, m2):
    for _ in range(2):
        r1_sq = float(np.dot(r1, r1))
        if r1_sq > 1e-12:
            v1 = v1 - r1 * (np.dot(r1, v1) / r1_sq)

        d = r2 - r1
        denom = float(np.dot(d, d)) * (1.0 / m1 + 1.0 / m2)
        if denom > 1e-12:
            constraint_speed = np.dot(d, v2 - v1)
            impulse = -constraint_speed / denom
            v1 = v1 - d * (impulse / m1)
            v2 = v2 + d * (impulse / m2)

    return v1, v2


def constrained_acceleration(r1, r2, v1, v2, m1, m2, l1, l2, g, stabilization):
    gravity = np.array([0.0, 0.0, -g], dtype=float)
    d = r2 - r1

    a11 = np.dot(r1, r1) / m1
    a12 = -np.dot(r1, d) / m1
    a22 = np.dot(d, d) * (1.0 / m1 + 1.0 / m2)
    system = np.array([[a11, a12], [a12, a22]], dtype=float)

    position_error = np.array(
        [
            0.5 * (np.dot(r1, r1) - l1 * l1),
            0.5 * (np.dot(d, d) - l2 * l2),
        ],
        dtype=float,
    )
    velocity_error = np.array(
        [
            np.dot(r1, v1),
            np.dot(d, v2 - v1),
        ],
        dtype=float,
    )
    geometric_terms = np.array(
        [
            np.dot(v1, v1),
            np.dot(v2 - v1, v2 - v1),
        ],
        dtype=float,
    )
    external_terms = np.array(
        [
            np.dot(r1, gravity),
            0.0,
        ],
        dtype=float,
    )
    rhs = -(
        external_terms
        + geometric_terms
        + 2.0 * stabilization * velocity_error
        + (stabilization**2) * position_error
    )

    lambda1, lambda2 = np.linalg.solve(system, rhs)
    a1 = gravity + (lambda1 * r1 - lambda2 * d) / m1
    a2 = gravity + (lambda2 * d) / m2
    return a1, a2


def simulate(
    duration=20.0,
    dt=0.005,
    m1=3.0,
    m2=3.0,
    l1=5,
    l2=3,
    g=9.81,
    azimuth1_deg=30.0,
    elevation1_deg=-55.0,
    azimuth2_deg=-35.0,
    elevation2_deg=20.0,
    omega1_vec=(0.0, 1.1, 0.4),
    omega2_vec=(0.8, -0.2, -0.5),
    stabilization=10.0,
):
    steps = int(duration / dt) + 1
    r1, r2, v1, v2 = initial_state(
        l1=l1,
        l2=l2,
        azimuth1_deg=azimuth1_deg,
        elevation1_deg=elevation1_deg,
        azimuth2_deg=azimuth2_deg,
        elevation2_deg=elevation2_deg,
        omega1_vec=omega1_vec,
        omega2_vec=omega2_vec,
    )
    r1, r2 = project_positions(r1, r2, l1, l2)
    v1, v2 = project_velocities(r1, r2, v1, v2, m1, m2)

    r1_history = np.zeros((steps, 3), dtype=float)
    r2_history = np.zeros((steps, 3), dtype=float)

    for index in range(steps):
        r1_history[index] = r1
        r2_history[index] = r2

        a1, a2 = constrained_acceleration(
            r1=r1,
            r2=r2,
            v1=v1,
            v2=v2,
            m1=m1,
            m2=m2,
            l1=l1,
            l2=l2,
            g=g,
            stabilization=stabilization,
        )
        v1 = v1 + a1 * dt
        v2 = v2 + a2 * dt
        r1 = r1 + v1 * dt
        r2 = r2 + v2 * dt

        r1, r2 = project_positions(r1, r2, l1, l2)
        v1, v2 = project_velocities(r1, r2, v1, v2, m1, m2)

    return r1_history, r2_history


def rotate_point(point, azimuth, elevation):
    cos_azimuth = math.cos(azimuth)
    sin_azimuth = math.sin(azimuth)
    x1 = cos_azimuth * point[0] + sin_azimuth * point[1]
    y1 = -sin_azimuth * point[0] + cos_azimuth * point[1]
    z1 = point[2]

    cos_elevation = math.cos(elevation)
    sin_elevation = math.sin(elevation)
    x2 = x1
    y2 = cos_elevation * y1 - sin_elevation * z1
    z2 = sin_elevation * y1 + cos_elevation * z1
    return np.array([x2, y2, z2], dtype=float)


def animate_pendulum(r1_history, r2_history, dt, keep_open=True):
    root = tk.Tk()
    root.title("3D Double Pendulum")
    root.geometry("1100x820")
    root.minsize(820, 620)

    header = tk.Frame(root, bg="#e2e8f0", height=36)
    header.pack(fill="x")
    status_label = tk.Label(
        header,
        text="3D Double Pendulum  |  drag: rotate view  |  wheel: zoom  |  q / Esc: close",
        bg="#e2e8f0",
        fg="#0f172a",
        anchor="w",
        padx=12,
        font=("Yu Gothic UI", 10, "bold"),
    )
    status_label.pack(fill="both", expand=True)

    canvas = tk.Canvas(root, bg="#f8fafc", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    all_points = np.vstack([np.zeros((1, 3)), r1_history, r2_history])
    limit = float(np.max(np.abs(all_points))) + 0.25

    state = {
        "frame": 0,
        "job": None,
        "running": True,
        "azimuth": math.radians(42.0),
        "elevation": math.radians(24.0),
        "zoom": 1.0,
        "last_mouse": None,
        "keep_open": keep_open,
    }

    axis_length = limit * 1.2
    camera_distance = max(4.0 * limit, 4.0)
    trace1_coords = []
    trace2_coords = []
    items = {}

    def close_window(_event=None):
        if not state["running"]:
            return
        state["running"] = False
        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None
        root.destroy()

    root.bind("<KeyPress-q>", close_window)
    root.bind("<Escape>", close_window)

    def project_point(point):
        rotated = rotate_point(point, state["azimuth"], state["elevation"])
        depth = rotated[2] + camera_distance
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        focal = min(width, height) * 0.42 * state["zoom"]
        scale = focal / max(depth, 0.2)
        sx = width / 2 + rotated[0] * scale
        sy = height / 2 + rotated[1] * scale
        return sx, sy, depth

    def project_polyline(points):
        coords = []
        for point in points:
            sx, sy, _ = project_point(point)
            coords.extend([sx, sy])
        return coords

    def set_circle(item_id, cx, cy, radius):
        canvas.coords(item_id, cx - radius, cy - radius, cx + radius, cy + radius)

    def rebuild_trace_coords():
        frame = state["frame"]
        trace1_coords.clear()
        trace2_coords.clear()

        for point in r1_history[: frame + 1]:
            sx, sy, _ = project_point(point)
            trace1_coords.extend([sx, sy])

        for point in r2_history[: frame + 1]:
            sx, sy, _ = project_point(point)
            trace2_coords.extend([sx, sy])

    def update_axes():
        origin = np.array([0.0, 0.0, 0.0], dtype=float)
        axes = [
            ("x_axis", "x_label", np.array([axis_length, 0.0, 0.0], dtype=float)),
            ("y_axis", "y_label", np.array([0.0, axis_length, 0.0], dtype=float)),
            ("z_axis", "z_label", np.array([0.0, 0.0, axis_length], dtype=float)),
        ]
        ox, oy, _ = project_point(origin)
        for line_key, label_key, endpoint in axes:
            ex, ey, _ = project_point(endpoint)
            canvas.coords(items[line_key], ox, oy, ex, ey)
            canvas.coords(items[label_key], ex + 10, ey)

    def update_scene():
        frame = state["frame"]
        canvas.itemconfigure(items["time"], text=f"t = {frame * dt:5.2f} s")
        update_axes()

        p0 = np.array([0.0, 0.0, 0.0], dtype=float)
        p1 = r1_history[frame]
        p2 = r2_history[frame]

        if len(trace1_coords) >= 4:
            canvas.coords(items["trace1"], *trace1_coords)
            canvas.itemconfigure(items["trace1"], state="normal")
        else:
            canvas.itemconfigure(items["trace1"], state="hidden")

        if len(trace2_coords) >= 4:
            canvas.coords(items["trace2"], *trace2_coords)
            canvas.itemconfigure(items["trace2"], state="normal")
        else:
            canvas.itemconfigure(items["trace2"], state="hidden")

        rod_coords = project_polyline([p0, p1, p2])
        canvas.coords(items["rod"], *rod_coords)

        projected = []
        for point, radius, color in (
            (p0, 5, items["origin"]),
            (p1, 9, items["bob1"]),
            (p2, 9, items["bob2"]),
        ):
            sx, sy, depth = project_point(point)
            projected.append((depth, sx, sy, radius, color))
            set_circle(color, sx, sy, radius)

        canvas.tag_raise(items["rod"])
        for _, _, _, _, item_id in sorted(projected, reverse=True):
            canvas.tag_raise(item_id)

    def on_resize(_event=None):
        if state["running"]:
            rebuild_trace_coords()
            update_scene()

    def step():
        if not state["running"]:
            return

        point1 = r1_history[state["frame"]]
        point2 = r2_history[state["frame"]]
        sx1, sy1, _ = project_point(point1)
        sx2, sy2, _ = project_point(point2)
        trace1_coords.extend([sx1, sy1])
        trace2_coords.extend([sx2, sy2])
        update_scene()
        if state["frame"] >= len(r1_history) - 1:
            if not state["keep_open"]:
                state["job"] = root.after(300, close_window)
            return

        state["frame"] += 1
        interval = max(1, int(dt * 1000))
        state["job"] = root.after(interval, step)

    def on_mouse_down(event):
        state["last_mouse"] = (event.x, event.y)

    def on_mouse_drag(event):
        if state["last_mouse"] is None:
            state["last_mouse"] = (event.x, event.y)
            return

        last_x, last_y = state["last_mouse"]
        dx = event.x - last_x
        dy = event.y - last_y
        state["last_mouse"] = (event.x, event.y)

        state["azimuth"] += dx * 0.01
        state["elevation"] = max(-1.4, min(1.4, state["elevation"] + dy * 0.01))
        rebuild_trace_coords()
        update_scene()

    def on_mouse_up(_event):
        state["last_mouse"] = None

    def apply_zoom(direction):
        factor = 1.1 if direction > 0 else 1 / 1.1
        state["zoom"] = max(0.25, min(5.0, state["zoom"] * factor))
        rebuild_trace_coords()
        update_scene()

    def on_mouse_wheel(event):
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return
        apply_zoom(1 if delta > 0 else -1)

    def on_scroll_up(_event):
        apply_zoom(1)

    def on_scroll_down(_event):
        apply_zoom(-1)

    canvas.bind("<ButtonPress-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_drag)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)
    canvas.bind("<MouseWheel>", on_mouse_wheel)
    canvas.bind("<Button-4>", on_scroll_up)
    canvas.bind("<Button-5>", on_scroll_down)
    canvas.bind("<Configure>", on_resize)

    root.update_idletasks()
    items["time"] = canvas.create_text(
        18,
        18,
        anchor="nw",
        text="t =  0.00 s",
        fill="#1f2937",
        font=("Consolas", 12),
    )
    items["x_axis"] = canvas.create_line(0, 0, 0, 0, fill="#ef4444", width=2)
    items["y_axis"] = canvas.create_line(0, 0, 0, 0, fill="#10b981", width=2)
    items["z_axis"] = canvas.create_line(0, 0, 0, 0, fill="#3b82f6", width=2)
    items["x_label"] = canvas.create_text(0, 0, text="X", fill="#ef4444", font=("Consolas", 12, "bold"))
    items["y_label"] = canvas.create_text(0, 0, text="Y", fill="#10b981", font=("Consolas", 12, "bold"))
    items["z_label"] = canvas.create_text(0, 0, text="Z", fill="#3b82f6", font=("Consolas", 12, "bold"))
    items["trace1"] = canvas.create_line(0, 0, 0, 0, fill="#f59e0b", width=2, state="hidden")
    items["trace2"] = canvas.create_line(0, 0, 0, 0, fill="#16a34a", width=2, state="hidden")
    items["rod"] = canvas.create_line(0, 0, 0, 0, 0, 0, fill="#1d4ed8", width=3)
    items["origin"] = canvas.create_oval(0, 0, 0, 0, fill="#111827", outline="")
    items["bob1"] = canvas.create_oval(0, 0, 0, 0, fill="#f97316", outline="")
    items["bob2"] = canvas.create_oval(0, 0, 0, 0, fill="#dc2626", outline="")
    update_scene()
    root.after(10, step)
    root.focus_force()
    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Animate a 3D double pendulum with persistent trajectories."
    )
    parser.add_argument("--duration", type=float, default=20.0, help="simulation time in seconds")
    parser.add_argument("--dt", type=float, default=0.005, help="time step in seconds")
    parser.add_argument("--azimuth1", type=float, default=30.0, help="first rod azimuth in degrees")
    parser.add_argument("--elevation1", type=float, default=-55.0, help="first rod elevation in degrees")
    parser.add_argument("--azimuth2", type=float, default=-35.0, help="second rod azimuth in degrees")
    parser.add_argument("--elevation2", type=float, default=20.0, help="second rod elevation in degrees")
    parser.add_argument("--omega1x", type=float, default=0.0, help="first rod angular velocity x")
    parser.add_argument("--omega1y", type=float, default=1.1, help="first rod angular velocity y")
    parser.add_argument("--omega1z", type=float, default=0.4, help="first rod angular velocity z")
    parser.add_argument("--omega2x", type=float, default=0.8, help="second rod angular velocity x")
    parser.add_argument("--omega2y", type=float, default=-0.2, help="second rod angular velocity y")
    parser.add_argument("--omega2z", type=float, default=-0.5, help="second rod angular velocity z")
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help="close the window automatically when the animation ends",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    r1_history, r2_history = simulate(
        duration=args.duration,
        dt=args.dt,
        azimuth1_deg=args.azimuth1,
        elevation1_deg=args.elevation1,
        azimuth2_deg=args.azimuth2,
        elevation2_deg=args.elevation2,
        omega1_vec=(args.omega1x, args.omega1y, args.omega1z),
        omega2_vec=(args.omega2x, args.omega2y, args.omega2z),
    )
    animate_pendulum(r1_history, r2_history, args.dt, keep_open=not args.auto_close)
