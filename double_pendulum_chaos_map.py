import argparse
import concurrent.futures as cf
import html
import math
import multiprocessing as mp
import tkinter as tk
from pathlib import Path

import numpy as np

WORKER_COUNT = 4
CELLS_PER_TASK = 64
PERTURBATION_DIRECTION = np.array([1.0, 0.0, 0.35, 0.0], dtype=np.float64)
PERTURBATION_DIRECTION /= np.linalg.norm(PERTURBATION_DIRECTION)


def wrap_angle(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def create_workspace(cell_count):
    state_shape = (cell_count, 4)
    scalar_shape = (cell_count,)
    return {
        "base": np.empty(state_shape, dtype=np.float64),
        "perturbed": np.empty(state_shape, dtype=np.float64),
        "difference": np.empty(state_shape, dtype=np.float64),
        "temp": np.empty(state_shape, dtype=np.float64),
        "k1": np.empty(state_shape, dtype=np.float64),
        "k2": np.empty(state_shape, dtype=np.float64),
        "k3": np.empty(state_shape, dtype=np.float64),
        "k4": np.empty(state_shape, dtype=np.float64),
        "delta": np.empty(scalar_shape, dtype=np.float64),
        "sin_delta": np.empty(scalar_shape, dtype=np.float64),
        "cos_delta": np.empty(scalar_shape, dtype=np.float64),
        "sin_theta1": np.empty(scalar_shape, dtype=np.float64),
        "sin_theta2": np.empty(scalar_shape, dtype=np.float64),
        "den1": np.empty(scalar_shape, dtype=np.float64),
        "den2": np.empty(scalar_shape, dtype=np.float64),
        "omega1_sq": np.empty(scalar_shape, dtype=np.float64),
        "omega2_sq": np.empty(scalar_shape, dtype=np.float64),
        "work1": np.empty(scalar_shape, dtype=np.float64),
        "work2": np.empty(scalar_shape, dtype=np.float64),
        "work3": np.empty(scalar_shape, dtype=np.float64),
        "distance": np.empty(scalar_shape, dtype=np.float64),
        "log_sum": np.zeros(scalar_shape, dtype=np.float64),
    }


def derivatives_batch(state, out, params, workspace):
    theta1 = state[:, 0]
    omega1 = state[:, 1]
    theta2 = state[:, 2]
    omega2 = state[:, 3]

    delta = workspace["delta"]
    sin_delta = workspace["sin_delta"]
    cos_delta = workspace["cos_delta"]
    sin_theta1 = workspace["sin_theta1"]
    sin_theta2 = workspace["sin_theta2"]
    den1 = workspace["den1"]
    den2 = workspace["den2"]
    omega1_sq = workspace["omega1_sq"]
    omega2_sq = workspace["omega2_sq"]
    work1 = workspace["work1"]
    work2 = workspace["work2"]
    work3 = workspace["work3"]

    np.subtract(theta2, theta1, out=delta)
    np.sin(delta, out=sin_delta)
    np.cos(delta, out=cos_delta)
    np.sin(theta1, out=sin_theta1)
    np.sin(theta2, out=sin_theta2)
    np.multiply(omega1, omega1, out=omega1_sq)
    np.multiply(omega2, omega2, out=omega2_sq)

    np.multiply(cos_delta, cos_delta, out=den1)
    den1 *= -(params["m2"] * params["l1"])
    den1 += (params["m1"] + params["m2"]) * params["l1"]
    np.multiply(den1, params["l2"] / params["l1"], out=den2)

    out[:, 0] = omega1
    out[:, 2] = omega2

    np.multiply(omega1_sq, sin_delta, out=work1)
    work1 *= params["m2"] * params["l1"]
    work1 *= cos_delta

    np.multiply(sin_theta2, cos_delta, out=work2)
    work2 *= params["m2"] * params["g"]
    work1 += work2

    np.multiply(omega2_sq, sin_delta, out=work2)
    work2 *= params["m2"] * params["l2"]
    work1 += work2

    np.multiply(sin_theta1, -(params["m1"] + params["m2"]) * params["g"], out=work2)
    work1 += work2
    np.divide(work1, den1, out=out[:, 1])

    np.multiply(omega2_sq, sin_delta, out=work1)
    work1 *= -params["m2"] * params["l2"]
    work1 *= cos_delta

    np.multiply(sin_theta1, params["g"], out=work2)
    work2 *= cos_delta

    np.multiply(omega1_sq, sin_delta, out=work3)
    work3 *= params["l1"]
    work2 -= work3

    np.multiply(sin_theta2, params["g"], out=work3)
    work2 -= work3

    work2 *= params["m1"] + params["m2"]
    work1 += work2
    np.divide(work1, den2, out=out[:, 3])


def rk4_step_inplace(state, params, workspace):
    half_dt = 0.5 * params["dt"]
    full_dt = params["dt"]
    sixth_dt = params["dt"] / 6.0
    third_dt = params["dt"] / 3.0

    k1 = workspace["k1"]
    k2 = workspace["k2"]
    k3 = workspace["k3"]
    k4 = workspace["k4"]
    temp = workspace["temp"]

    derivatives_batch(state, k1, params, workspace)

    np.copyto(temp, k1)
    temp *= half_dt
    temp += state
    derivatives_batch(temp, k2, params, workspace)

    np.copyto(temp, k2)
    temp *= half_dt
    temp += state
    derivatives_batch(temp, k3, params, workspace)

    np.copyto(temp, k3)
    temp *= full_dt
    temp += state
    derivatives_batch(temp, k4, params, workspace)

    np.copyto(temp, k1)
    temp *= sixth_dt
    state += temp

    np.copyto(temp, k2)
    temp *= third_dt
    state += temp

    np.copyto(temp, k3)
    temp *= third_dt
    state += temp

    np.copyto(temp, k4)
    temp *= sixth_dt
    state += temp


def finite_time_lyapunov_batch(
    theta1_deg,
    theta2_deg,
    omega1,
    omega2,
    m1,
    m2,
    l1,
    l2,
    g,
    dt,
    duration,
    perturbation=1e-8,
    renorm_interval_steps=5,
):
    cell_count = int(len(theta1_deg))
    if cell_count == 0:
        return np.empty(0, dtype=np.float64)

    params = {
        "m1": float(m1),
        "m2": float(m2),
        "l1": float(l1),
        "l2": float(l2),
        "g": float(g),
        "dt": float(dt),
    }
    workspace = create_workspace(cell_count)
    base = workspace["base"]
    perturbed = workspace["perturbed"]
    difference = workspace["difference"]
    temp = workspace["temp"]
    distance = workspace["distance"]
    log_sum = workspace["log_sum"]

    np.radians(theta1_deg, out=base[:, 0])
    base[:, 1].fill(float(omega1))
    np.radians(theta2_deg, out=base[:, 2])
    base[:, 3].fill(float(omega2))

    np.copyto(perturbed, base)
    perturbed += perturbation * PERTURBATION_DIRECTION

    steps = max(1, int(duration / dt))
    renorm_count = 0

    for step in range(steps):
        rk4_step_inplace(base, params, workspace)
        rk4_step_inplace(perturbed, params, workspace)

        if (step + 1) % renorm_interval_steps != 0:
            continue

        difference[:, 0] = wrap_angle(perturbed[:, 0] - base[:, 0])
        difference[:, 1] = perturbed[:, 1] - base[:, 1]
        difference[:, 2] = wrap_angle(perturbed[:, 2] - base[:, 2])
        difference[:, 3] = perturbed[:, 3] - base[:, 3]

        np.copyto(temp, difference)
        np.square(temp, out=temp)
        np.sum(temp, axis=1, out=distance)
        np.sqrt(distance, out=distance)
        np.maximum(distance, 1e-16, out=distance)

        log_sum += np.log(distance / perturbation)
        renorm_count += 1

        difference *= (perturbation / distance)[:, None]
        np.copyto(perturbed, base)
        perturbed += difference

    total_time = max(renorm_count * renorm_interval_steps * dt, dt)
    np.maximum(log_sum / total_time, 0.0, out=log_sum)
    return log_sum.copy()


def finite_time_lyapunov(
    theta1_deg,
    theta2_deg,
    omega1,
    omega2,
    m1,
    m2,
    l1,
    l2,
    g,
    dt,
    duration,
    perturbation=1e-8,
    renorm_interval_steps=5,
):
    return float(
        finite_time_lyapunov_batch(
            np.array([theta1_deg], dtype=np.float64),
            np.array([theta2_deg], dtype=np.float64),
            omega1,
            omega2,
            m1,
            m2,
            l1,
            l2,
            g,
            dt,
            duration,
            perturbation=perturbation,
            renorm_interval_steps=renorm_interval_steps,
        )[0]
    )


def interpolate_color(stops, value):
    value = min(1.0, max(0.0, value))
    for index in range(len(stops) - 1):
        left_value, left_color = stops[index]
        right_value, right_color = stops[index + 1]
        if value <= right_value:
            local = 0.0 if right_value == left_value else (value - left_value) / (right_value - left_value)
            return tuple(
                int(round(left_color[channel] + local * (right_color[channel] - left_color[channel])))
                for channel in range(3)
            )
    return stops[-1][1]


def rgb_to_hex(color):
    return "#{:02x}{:02x}{:02x}".format(*color)


def value_range_for_heatmap(values):
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 1.0
    vmax = max(1e-9, float(np.quantile(finite, 0.98)))
    return 0.0, vmax


def resolve_output_path(path_text):
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path


def save_heatmap_svg(file_path, values, theta_min, theta_max, params_text, color_stops):
    file_path = resolve_output_path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    width = 1180
    height = 860
    left = 70
    top = 110
    right = width - 110
    bottom = height - 70
    bar_width = 28
    plot_right = right - bar_width - 26
    grid = values.shape[0]
    vmin, vmax = value_range_for_heatmap(values)
    cell_width = (plot_right - left) / max(grid, 1)
    cell_height = (bottom - top) / max(grid, 1)

    parts = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"#e2e8f0\"/>",
        "<style>",
        "text{font-family:'Segoe UI','Yu Gothic UI',sans-serif}",
        ".mono{font-family:Consolas,'Courier New',monospace}",
        "</style>",
        "<text x=\"24\" y=\"34\" font-size=\"18\" font-weight=\"700\" fill=\"#0f172a\">Chaos Map by Finite-Time Lyapunov Exponent</text>",
        "<text x=\"24\" y=\"58\" font-size=\"11\" fill=\"#334155\">theta1-theta2 plane. Dark blue is regular-like, warm colors are more chaotic-like.</text>",
        f"<text x=\"24\" y=\"80\" font-size=\"10\" fill=\"#475569\">{html.escape(params_text)}</text>",
        f"<rect x=\"{left}\" y=\"{top}\" width=\"{plot_right - left}\" height=\"{bottom - top}\" fill=\"#f8fafc\" stroke=\"#cbd5e1\"/>",
    ]

    for row in range(grid):
        for col in range(grid):
            value = values[row, col]
            if not np.isfinite(value):
                continue
            normalized = 0.0 if vmax <= vmin else (value - vmin) / (vmax - vmin)
            color = rgb_to_hex(interpolate_color(color_stops, normalized))
            x0 = left + col * cell_width
            y0 = top + row * cell_height
            parts.append(
                f"<rect x=\"{x0:.3f}\" y=\"{y0:.3f}\" width=\"{cell_width + 1:.3f}\" height=\"{cell_height + 1:.3f}\" fill=\"{color}\" stroke=\"{color}\"/>"
            )

    for angle_deg, label in [(-180, "-180"), (-90, "-90"), (0, "0"), (90, "90"), (180, "180")]:
        x = left + (angle_deg - theta_min) / (theta_max - theta_min) * (plot_right - left)
        y = top + (theta_max - angle_deg) / (theta_max - theta_min) * (bottom - top)
        parts.append(f"<line x1=\"{x:.3f}\" y1=\"{bottom}\" x2=\"{x:.3f}\" y2=\"{bottom + 6}\" stroke=\"#475569\"/>")
        parts.append(f"<text x=\"{x:.3f}\" y=\"{bottom + 22}\" text-anchor=\"middle\" class=\"mono\" font-size=\"10\" fill=\"#475569\">{label}</text>")
        parts.append(f"<line x1=\"{left - 6}\" y1=\"{y:.3f}\" x2=\"{left}\" y2=\"{y:.3f}\" stroke=\"#475569\"/>")
        parts.append(f"<text x=\"{left - 10}\" y=\"{y + 3:.3f}\" text-anchor=\"end\" class=\"mono\" font-size=\"10\" fill=\"#475569\">{label}</text>")

    parts.extend(
        [
            f"<text x=\"{(left + plot_right) / 2.0:.3f}\" y=\"{bottom + 42}\" text-anchor=\"middle\" font-size=\"10\" font-weight=\"700\" fill=\"#334155\">theta1 (deg)</text>",
            f"<text x=\"{left - 42}\" y=\"{(top + bottom) / 2.0:.3f}\" text-anchor=\"middle\" transform=\"rotate(-90 {left - 42} {(top + bottom) / 2.0:.3f})\" font-size=\"10\" font-weight=\"700\" fill=\"#334155\">theta2 (deg)</text>",
        ]
    )

    bar_x0 = plot_right + 28
    bar_y0 = top
    bar_y1 = bottom
    steps = 120
    for index in range(steps):
        t0 = index / steps
        t1 = (index + 1) / steps
        color = rgb_to_hex(interpolate_color(color_stops, 1.0 - t0))
        y0 = bar_y0 + t0 * (bar_y1 - bar_y0)
        y1 = bar_y0 + t1 * (bar_y1 - bar_y0)
        parts.append(
            f"<rect x=\"{bar_x0}\" y=\"{y0:.3f}\" width=\"{bar_width}\" height=\"{y1 - y0:.3f}\" fill=\"{color}\" stroke=\"{color}\"/>"
        )

    parts.extend(
        [
            f"<rect x=\"{bar_x0}\" y=\"{bar_y0}\" width=\"{bar_width}\" height=\"{bar_y1 - bar_y0}\" fill=\"none\" stroke=\"#334155\"/>",
            f"<text x=\"{bar_x0 + bar_width / 2.0:.3f}\" y=\"{bar_y0 - 18}\" text-anchor=\"middle\" font-size=\"10\" font-weight=\"700\" fill=\"#334155\">FTLE</text>",
            f"<text x=\"{bar_x0 + bar_width + 12}\" y=\"{bar_y0 + 4}\" font-size=\"10\" class=\"mono\" fill=\"#475569\">{vmax:.3f}</text>",
            f"<text x=\"{bar_x0 + bar_width + 12}\" y=\"{bar_y1 + 4}\" font-size=\"10\" class=\"mono\" fill=\"#475569\">{vmin:.3f}</text>",
            "</svg>",
        ]
    )

    file_path.write_text("\n".join(parts), encoding="utf-8")
    return file_path


def build_cell_tasks(theta_min, theta_max, grid, cells_per_task):
    del theta_min, theta_max
    total_cells = grid * grid
    return [
        (start, min(start + cells_per_task, total_cells))
        for start in range(0, total_cells, cells_per_task)
    ]


def compute_cell_batch(cell_range, params):
    start, stop = cell_range
    grid = params["grid"]
    theta_values = params["theta_values"]
    indices = np.arange(start, stop, dtype=np.int32)
    rows = indices // grid
    cols = indices % grid

    values = finite_time_lyapunov_batch(
        theta1_deg=theta_values[cols],
        theta2_deg=theta_values[grid - 1 - rows],
        omega1=params["omega1"],
        omega2=params["omega2"],
        m1=params["m1"],
        m2=params["m2"],
        l1=params["l1"],
        l2=params["l2"],
        g=params["g"],
        dt=params["dt"],
        duration=params["duration"],
    )
    return rows, cols, values


def show_chaos_map(duration, dt, auto_close_ms=0):
    root = tk.Tk()
    root.title("Double Pendulum Chaos Map")
    root.geometry("1180x860")
    root.minsize(920, 700)

    controls = tk.Frame(root, bg="#cbd5e1", padx=12, pady=10)
    controls.pack(fill="x")
    canvas = tk.Canvas(root, bg="#e2e8f0", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    vars_map = {
        "m1": tk.StringVar(value="1.1"),
        "m2": tk.StringVar(value="1.0"),
        "l1": tk.StringVar(value="1.0"),
        "l2": tk.StringVar(value="1.0"),
        "omega1": tk.StringVar(value="0.0"),
        "omega2": tk.StringVar(value="0.0"),
        "grid": tk.StringVar(value="60"),
        "duration": tk.StringVar(value=f"{duration:.3g}"),
        "dt": tk.StringVar(value=f"{dt:.3g}"),
        "save_svg": tk.StringVar(value="docs/images/chaos_heatmap_sample.svg"),
    }

    state = {
        "generation": 0,
        "grid": 0,
        "values": np.empty((0, 0), dtype=float),
        "running": False,
        "job": None,
        "executor": None,
        "futures": {},
        "tasks": [],
        "next_task_index": 0,
        "completed_cells": 0,
        "params_text": "",
        "duration": duration,
        "dt": dt,
        "theta_min": -180.0,
        "theta_max": 180.0,
    }

    color_stops = [
        (0.0, (15, 23, 42)),
        (0.22, (37, 99, 235)),
        (0.48, (6, 182, 212)),
        (0.72, (245, 158, 11)),
        (1.0, (220, 38, 38)),
    ]

    def make_labeled_entry(parent, label, variable, width=8):
        frame = tk.Frame(parent, bg="#cbd5e1")
        frame.pack(side="left", padx=(0, 10))
        tk.Label(frame, text=label, bg="#cbd5e1", fg="#0f172a", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
        tk.Entry(frame, textvariable=variable, width=width, font=("Consolas", 11)).pack()

    make_labeled_entry(controls, "m1", vars_map["m1"])
    make_labeled_entry(controls, "m2", vars_map["m2"])
    make_labeled_entry(controls, "l1", vars_map["l1"])
    make_labeled_entry(controls, "l2", vars_map["l2"])
    make_labeled_entry(controls, "omega1", vars_map["omega1"])
    make_labeled_entry(controls, "omega2", vars_map["omega2"])
    make_labeled_entry(controls, "grid", vars_map["grid"], width=6)
    make_labeled_entry(controls, "duration", vars_map["duration"], width=7)
    make_labeled_entry(controls, "dt", vars_map["dt"], width=7)
    make_labeled_entry(controls, "save_svg", vars_map["save_svg"], width=28)

    status_var = tk.StringVar(value="Ready")
    status_label = tk.Label(
        controls,
        textvariable=status_var,
        bg="#cbd5e1",
        fg="#334155",
        font=("Yu Gothic UI", 10),
        padx=12,
    )
    status_label.pack(side="right")

    def shutdown_executor():
        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None

        for future in list(state["futures"]):
            future.cancel()
        state["futures"].clear()

        executor = state["executor"]
        state["executor"] = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def close_window():
        state["running"] = False
        shutdown_executor()
        root.destroy()

    def parse_positive_float(name):
        value = float(vars_map[name].get())
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
        return value

    def parse_float(name):
        return float(vars_map[name].get())

    def parse_grid():
        value = int(vars_map["grid"].get())
        if value < 8 or value > 400:
            raise ValueError("grid must be between 8 and 400.")
        return value

    def value_range():
        return value_range_for_heatmap(state["values"])

    def save_current_svg(show_status=True):
        target = vars_map["save_svg"].get().strip()
        if not target:
            if show_status:
                status_var.set("save_svg is empty")
            return None

        if state["grid"] <= 0 or not state["values"].size or not np.isfinite(state["values"]).any():
            if show_status:
                status_var.set("No heatmap data to save yet")
            return None

        try:
            saved_path = save_heatmap_svg(
                file_path=target,
                values=state["values"],
                theta_min=state["theta_min"],
                theta_max=state["theta_max"],
                params_text=state["params_text"],
                color_stops=color_stops,
            )
        except Exception as exc:
            if show_status:
                status_var.set(f"Save failed: {exc}")
            return None

        if show_status:
            status_var.set(f"Saved SVG: {saved_path}")
        return saved_path

    def redraw(_event=None):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        canvas.create_text(
            24,
            16,
            anchor="nw",
            text="Chaos Map by Finite-Time Lyapunov Exponent",
            fill="#0f172a",
            font=("Yu Gothic UI", 18, "bold"),
        )
        canvas.create_text(
            24,
            46,
            anchor="nw",
            text="theta1-theta2 plane. Dark blue is regular-like, warm colors are more chaotic-like.",
            fill="#334155",
            font=("Yu Gothic UI", 11),
        )
        canvas.create_text(
            24,
            68,
            anchor="nw",
            text=state["params_text"],
            fill="#475569",
            font=("Yu Gothic UI", 10),
        )

        left = 70
        top = 110
        right = width - 110
        bottom = height - 70
        bar_width = 28
        plot_right = right - bar_width - 26

        canvas.create_rectangle(left, top, plot_right, bottom, fill="#f8fafc", outline="#cbd5e1")

        if state["grid"] > 0 and state["values"].size:
            vmin, vmax = value_range()
            cell_width = (plot_right - left) / state["grid"]
            cell_height = (bottom - top) / state["grid"]

            for row in range(state["grid"]):
                for col in range(state["grid"]):
                    value = state["values"][row, col]
                    if not np.isfinite(value):
                        continue
                    normalized = 0.0 if vmax <= vmin else (value - vmin) / (vmax - vmin)
                    color = rgb_to_hex(interpolate_color(color_stops, normalized))
                    x0 = left + col * cell_width
                    y0 = top + row * cell_height
                    x1 = x0 + cell_width + 1
                    y1 = y0 + cell_height + 1
                    canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)

            for angle_deg, label in [(-180, "-180"), (-90, "-90"), (0, "0"), (90, "90"), (180, "180")]:
                x = left + (angle_deg - state["theta_min"]) / (state["theta_max"] - state["theta_min"]) * (plot_right - left)
                canvas.create_line(x, bottom, x, bottom + 6, fill="#475569")
                canvas.create_text(x, bottom + 22, text=label, fill="#475569", font=("Consolas", 10))

                y = top + (state["theta_max"] - angle_deg) / (state["theta_max"] - state["theta_min"]) * (bottom - top)
                canvas.create_line(left - 6, y, left, y, fill="#475569")
                canvas.create_text(left - 10, y, text=label, anchor="e", fill="#475569", font=("Consolas", 10))

            canvas.create_text((left + plot_right) / 2.0, bottom + 42, text="theta1 (deg)", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
            canvas.create_text(left - 42, (top + bottom) / 2.0, text="theta2 (deg)", angle=90, fill="#334155", font=("Yu Gothic UI", 10, "bold"))

            bar_x0 = plot_right + 28
            bar_y0 = top
            bar_y1 = bottom
            steps = 120
            for index in range(steps):
                t0 = index / steps
                t1 = (index + 1) / steps
                color = rgb_to_hex(interpolate_color(color_stops, 1.0 - t0))
                y0 = bar_y0 + t0 * (bar_y1 - bar_y0)
                y1 = bar_y0 + t1 * (bar_y1 - bar_y0)
                canvas.create_rectangle(bar_x0, y0, bar_x0 + bar_width, y1, fill=color, outline=color)
            canvas.create_rectangle(bar_x0, bar_y0, bar_x0 + bar_width, bar_y1, outline="#334155")
            canvas.create_text(bar_x0 + bar_width / 2.0, bar_y0 - 18, text="FTLE", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
            canvas.create_text(bar_x0 + bar_width + 12, bar_y0, anchor="w", text=f"{vmax:.3f}", fill="#475569", font=("Consolas", 10))
            canvas.create_text(bar_x0 + bar_width + 12, bar_y1, anchor="w", text=f"{vmin:.3f}", fill="#475569", font=("Consolas", 10))

        if state["running"]:
            total_cells = max(1, state["grid"] * state["grid"])
            progress = int(round(100 * state["completed_cells"] / total_cells))
            canvas.create_text(
                width - 24,
                18,
                anchor="ne",
                text=f"Calculating {progress}%",
                fill="#0f172a",
                font=("Yu Gothic UI", 11, "bold"),
            )

    def submit_tasks(generation, params):
        if generation != state["generation"] or not state["running"]:
            return

        while (
            state["executor"] is not None
            and len(state["futures"]) < WORKER_COUNT
            and state["next_task_index"] < len(state["tasks"])
        ):
            cell_range = state["tasks"][state["next_task_index"]]
            state["next_task_index"] += 1
            future = state["executor"].submit(compute_cell_batch, cell_range, params)
            state["futures"][future] = cell_range[1] - cell_range[0]

    def poll_results(generation, params):
        if generation != state["generation"] or not state["running"]:
            return

        total_cells = state["grid"] * state["grid"]
        finished = [future for future in state["futures"] if future.done()]

        for future in finished:
            batch_size = state["futures"].pop(future)
            try:
                rows, cols, values = future.result()
            except Exception as exc:
                state["running"] = False
                shutdown_executor()
                status_var.set(f"Worker error: {exc}")
                compute_button.config(state="normal")
                stop_button.config(state="disabled")
                redraw()
                return

            state["values"][rows, cols] = values
            state["completed_cells"] += batch_size

        if finished:
            status_var.set(f"Calculating {state['completed_cells']}/{total_cells} cells")
            redraw()
            root.update_idletasks()

        if state["completed_cells"] >= total_cells:
            state["running"] = False
            shutdown_executor()
            compute_button.config(state="normal")
            stop_button.config(state="disabled")
            saved_path = save_current_svg(show_status=False)
            if saved_path is not None:
                status_var.set(f"Done and saved: {saved_path}")
            else:
                status_var.set("Done")
            redraw()
            return

        submit_tasks(generation, params)
        state["job"] = root.after(25, lambda: poll_results(generation, params))

    def stop_compute():
        if not state["running"]:
            return

        state["generation"] += 1
        state["running"] = False
        shutdown_executor()
        total_cells = max(1, state["grid"] * state["grid"])
        status_var.set(f"Stopped at {state['completed_cells']}/{total_cells} cells")
        compute_button.config(state="normal")
        stop_button.config(state="disabled")
        redraw()

    def start_compute():
        try:
            params = {
                "m1": parse_positive_float("m1"),
                "m2": parse_positive_float("m2"),
                "l1": parse_positive_float("l1"),
                "l2": parse_positive_float("l2"),
                "omega1": parse_float("omega1"),
                "omega2": parse_float("omega2"),
                "duration": parse_positive_float("duration"),
                "dt": parse_positive_float("dt"),
                "g": 9.81,
            }
            grid = parse_grid()
        except ValueError as exc:
            status_var.set(str(exc))
            return

        shutdown_executor()

        state["generation"] += 1
        state["grid"] = grid
        state["values"] = np.full((grid, grid), np.nan, dtype=float)
        state["running"] = True
        state["next_task_index"] = 0
        state["completed_cells"] = 0
        params["grid"] = grid
        params["theta_values"] = np.linspace(state["theta_min"], state["theta_max"], grid, dtype=np.float64)
        state["tasks"] = build_cell_tasks(
            theta_min=state["theta_min"],
            theta_max=state["theta_max"],
            grid=grid,
            cells_per_task=CELLS_PER_TASK,
        )
        state["executor"] = cf.ProcessPoolExecutor(
            max_workers=WORKER_COUNT,
            mp_context=mp.get_context("spawn"),
        )
        state["params_text"] = (
            f"m1={params['m1']:.3g}, m2={params['m2']:.3g}, l1={params['l1']:.3g}, l2={params['l2']:.3g}, "
            f"omega1={params['omega1']:.3g}, omega2={params['omega2']:.3g}, duration={params['duration']:.3g}, dt={params['dt']:.3g}, "
            f"workers={WORKER_COUNT}, batch={CELLS_PER_TASK}"
        )
        status_var.set(f"Calculating 0/{grid * grid} cells")
        compute_button.config(state="disabled")
        stop_button.config(state="normal")
        redraw()
        root.update_idletasks()
        submit_tasks(state["generation"], params)
        state["job"] = root.after(25, lambda: poll_results(state["generation"], params))

    compute_button = tk.Button(
        controls,
        text="Compute Heatmap",
        command=start_compute,
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        padx=14,
        pady=4,
    )
    compute_button.pack(side="left", padx=(4, 8))

    stop_button = tk.Button(
        controls,
        text="Stop",
        command=stop_compute,
        bg="#ef4444",
        fg="white",
        activebackground="#dc2626",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        padx=14,
        pady=4,
        state="disabled",
    )
    stop_button.pack(side="left", padx=(0, 8))

    save_button = tk.Button(
        controls,
        text="Save Current",
        command=save_current_svg,
        bg="#0f766e",
        fg="white",
        activebackground="#115e59",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        padx=14,
        pady=4,
    )
    save_button.pack(side="left", padx=(0, 8))

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.bind("<Configure>", redraw)
    root.bind("<KeyPress-q>", lambda _event: close_window())
    root.bind("<Escape>", lambda _event: close_window())
    root.after(0, start_compute)
    root.focus_force()

    if auto_close_ms > 0:
        root.after(auto_close_ms, root.destroy)

    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Show a theta1-theta2 chaos heatmap for a double pendulum.")
    parser.add_argument("--duration", type=float, default=40.0, help="integration time for each grid cell")
    parser.add_argument("--dt", type=float, default=0.02, help="time step")
    parser.add_argument("--auto-close-ms", type=int, default=0, help="auto close the window after N milliseconds")
    return parser.parse_args()


if __name__ == "__main__":
    mp.freeze_support()
    args = parse_args()
    show_chaos_map(duration=args.duration, dt=args.dt, auto_close_ms=args.auto_close_ms)
