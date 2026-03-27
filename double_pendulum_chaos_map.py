import argparse
import concurrent.futures as cf
import math
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    import psutil
except ImportError:
    psutil = None

DEFAULT_WORKER_COUNT = 48
DEFAULT_CELLS_PER_TASK = 192
DEFAULT_MAX_IN_FLIGHT = DEFAULT_WORKER_COUNT * 4
DEFAULT_POLL_INTERVAL_MS = 4
MAX_WINDOWS_WORKERS = 61
AUTO_MIN_CELLS_PER_TASK = 64
AUTO_MAX_CELLS_PER_TASK = 8192
AUTO_TARGET_TASK_SECONDS = 0.75
AUTO_MIN_TASK_SECONDS = 0.35
AUTO_MAX_TASK_SECONDS = 1.60
AUTO_MEMORY_PER_WORKER_BYTES = 512 * 1024 * 1024
MAX_STATE_ABS_VALUE = 1.0e6
PERTURBATION_DIRECTION = np.array([1.0, 0.0, 0.35, 0.0], dtype=np.float64)
PERTURBATION_DIRECTION /= np.linalg.norm(PERTURBATION_DIRECTION)


def format_filename_value(value):
    text = f"{value:.6g}"
    return text.replace("-", "neg").replace(".", "p")


def build_save_filename(params):
    parts = [
        "chaos_heatmap",
        f"m1-{format_filename_value(params['m1'])}",
        f"m2-{format_filename_value(params['m2'])}",
        f"l1-{format_filename_value(params['l1'])}",
        f"l2-{format_filename_value(params['l2'])}",
        f"o1-{format_filename_value(params['omega1'])}",
        f"o2-{format_filename_value(params['omega2'])}",
        f"grid-{int(params['grid'])}",
        f"dur-{format_filename_value(params['duration'])}",
        f"dt-{format_filename_value(params['dt'])}",
    ]
    return "_".join(parts) + ".png"


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def round_cells_per_task(value):
    rounded = int(math.ceil(max(1.0, float(value)) / 64.0) * 64)
    return clamp(rounded, AUTO_MIN_CELLS_PER_TASK, AUTO_MAX_CELLS_PER_TASK)


def get_system_resources():
    logical_cores = os.cpu_count() or 1
    physical_cores = None
    available_memory = None

    if psutil is not None:
        try:
            physical_cores = psutil.cpu_count(logical=False)
        except Exception:
            physical_cores = None
        try:
            available_memory = int(psutil.virtual_memory().available)
        except Exception:
            available_memory = None

    if not physical_cores:
        physical_cores = max(1, logical_cores // 2)

    return {
        "logical_cores": logical_cores,
        "physical_cores": physical_cores,
        "available_memory": available_memory,
    }


def choose_worker_count(total_cells, resources):
    memory_limited_workers = MAX_WINDOWS_WORKERS
    if resources["available_memory"] is not None:
        memory_limited_workers = max(1, resources["available_memory"] // AUTO_MEMORY_PER_WORKER_BYTES)

    preferred_workers = int(resources["logical_cores"])
    if resources["logical_cores"] > resources["physical_cores"]:
        preferred_workers = min(
            MAX_WINDOWS_WORKERS,
            int(resources["logical_cores"] + max(1, resources["physical_cores"] // 2)),
        )

    return max(
        1,
        min(
            int(total_cells),
            preferred_workers,
            int(memory_limited_workers),
            MAX_WINDOWS_WORKERS,
        ),
    )


def choose_poll_interval_ms(task_seconds):
    if task_seconds <= 0.25:
        return 2
    if task_seconds <= 0.60:
        return 4
    if task_seconds <= 1.20:
        return 6
    if task_seconds <= 2.00:
        return 8
    return 12


def choose_in_flight_multiplier(task_seconds):
    if task_seconds <= 0.25:
        return 14
    if task_seconds <= 0.60:
        return 10
    if task_seconds <= 1.20:
        return 8
    if task_seconds <= 2.00:
        return 6
    return 4


def benchmark_cells_per_task(params, total_cells):
    if total_cells <= 0:
        return {
            "sample_cells": 0,
            "sample_seconds": 0.0,
            "cells_per_task": DEFAULT_CELLS_PER_TASK,
            "estimated_task_seconds": 0.0,
        }

    sample_cells = min(total_cells, max(AUTO_MIN_CELLS_PER_TASK, min(256, total_cells)))
    sample_cells = round_cells_per_task(sample_cells)
    sample_cells = min(sample_cells, total_cells)

    started_at = time.perf_counter()
    compute_cell_batch((0, sample_cells), params)
    elapsed = max(time.perf_counter() - started_at, 1e-6)
    cells_per_second = sample_cells / elapsed
    estimated_cells = round_cells_per_task(cells_per_second * AUTO_TARGET_TASK_SECONDS)
    estimated_cells = min(estimated_cells, total_cells)
    estimated_task_seconds = estimated_cells / cells_per_second

    return {
        "sample_cells": sample_cells,
        "sample_seconds": elapsed,
        "cells_per_task": estimated_cells,
        "estimated_task_seconds": estimated_task_seconds,
    }


def choose_auto_execution_settings(params):
    total_cells = int(params["grid"] * params["grid"])
    resources = get_system_resources()
    benchmark = benchmark_cells_per_task(params, total_cells)
    cells_per_task = benchmark["cells_per_task"]
    estimated_task_seconds = benchmark["estimated_task_seconds"]
    estimated_task_count = max(1, math.ceil(total_cells / max(1, cells_per_task)))
    worker_count = min(choose_worker_count(total_cells, resources), estimated_task_count)
    in_flight_multiplier = choose_in_flight_multiplier(estimated_task_seconds)
    max_in_flight = min(max(1, worker_count * in_flight_multiplier), estimated_task_count)
    poll_interval_ms = choose_poll_interval_ms(estimated_task_seconds)

    return {
        "resources": resources,
        "benchmark": benchmark,
        "worker_count": worker_count,
        "cells_per_task": cells_per_task,
        "max_in_flight": max_in_flight,
        "poll_interval_ms": poll_interval_ms,
    }


def wrap_angle(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def finite_state_mask(*states):
    if not states:
        return np.empty(0, dtype=bool)

    mask = np.ones(states[0].shape[0], dtype=bool)
    for state in states:
        mask &= np.all(np.isfinite(state), axis=1)
        mask &= np.max(np.abs(state), axis=1) <= MAX_STATE_ABS_VALUE
    return mask


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
    active = np.ones(cell_count, dtype=bool)

    for step in range(steps):
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            rk4_step_inplace(base, params, workspace)
            rk4_step_inplace(perturbed, params, workspace)

        stable = finite_state_mask(base, perturbed)
        newly_invalid = active & ~stable
        if newly_invalid.any():
            active[newly_invalid] = False
            base[newly_invalid] = 0.0
            perturbed[newly_invalid] = 0.0
            log_sum[newly_invalid] = np.nan

        if not active.any():
            break

        if (step + 1) % renorm_interval_steps != 0:
            continue

        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            difference[:, 0] = wrap_angle(perturbed[:, 0] - base[:, 0])
            difference[:, 1] = perturbed[:, 1] - base[:, 1]
            difference[:, 2] = wrap_angle(perturbed[:, 2] - base[:, 2])
            difference[:, 3] = perturbed[:, 3] - base[:, 3]

            np.copyto(temp, difference)
            np.square(temp, out=temp)
            np.sum(temp, axis=1, out=distance)
            np.sqrt(distance, out=distance)

        active_distance = np.maximum(distance[active], 1e-16)

        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            log_sum[active] += np.log(active_distance / perturbation)
        renorm_count += 1

        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            difference[active] *= (perturbation / active_distance)[:, None]
        perturbed[active] = base[active]
        perturbed[active] += difference[active]

        stable = finite_state_mask(base, perturbed)
        newly_invalid = active & ~stable
        if newly_invalid.any():
            active[newly_invalid] = False
            base[newly_invalid] = 0.0
            perturbed[newly_invalid] = 0.0
            log_sum[newly_invalid] = np.nan
        if not active.any():
            break

    total_time = max(renorm_count * renorm_interval_steps * dt, dt)
    result = np.full(cell_count, np.nan, dtype=np.float64)
    if active.any():
        result[active] = np.maximum(log_sum[active] / total_time, 0.0)
    return result


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


def representative_finite_mask(values, theta1_min, theta1_max, theta2_min, theta2_max):
    finite = np.isfinite(values)
    if not finite.any():
        return finite

    if (
        values.shape[0] > 2
        and values.shape[1] > 2
        and abs((theta1_max - theta1_min) - 360.0) < 1e-9
        and abs((theta2_max - theta2_min) - 360.0) < 1e-9
    ):
        interior = finite.copy()
        interior[0, :] = False
        interior[-1, :] = False
        interior[:, 0] = False
        interior[:, -1] = False
        if interior.any():
            return interior

    return finite


def value_range_for_heatmap(values, theta1_min, theta1_max, theta2_min, theta2_max):
    finite_mask = representative_finite_mask(values, theta1_min, theta1_max, theta2_min, theta2_max)
    finite = values[finite_mask]
    if finite.size == 0:
        return 0.0, 1.0
    vmax = max(1e-9, float(np.max(finite)))
    return 0.0, vmax


def resolve_output_path(path_text):
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return path


def build_heatmap_rgb(values, color_stops, theta1_min, theta1_max, theta2_min, theta2_max):
    height, width = values.shape
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[:] = np.array((226, 232, 240), dtype=np.uint8)

    finite = np.isfinite(values)
    if not finite.any():
        return rgb

    vmin, vmax = value_range_for_heatmap(values, theta1_min, theta1_max, theta2_min, theta2_max)
    normalized = np.zeros(values.shape, dtype=np.float64)
    if vmax > vmin:
        normalized[finite] = np.clip((values[finite] - vmin) / (vmax - vmin), 0.0, 1.0)

    for index in range(len(color_stops) - 1):
        left_value, left_color = color_stops[index]
        right_value, right_color = color_stops[index + 1]
        if index == len(color_stops) - 2:
            mask = finite & (normalized >= left_value) & (normalized <= right_value)
        else:
            mask = finite & (normalized >= left_value) & (normalized < right_value)
        if not mask.any():
            continue

        if right_value == left_value:
            local = np.zeros(np.count_nonzero(mask), dtype=np.float64)
        else:
            local = (normalized[mask] - left_value) / (right_value - left_value)

        for channel in range(3):
            channel_values = left_color[channel] + local * (right_color[channel] - left_color[channel])
            rgb[..., channel][mask] = np.rint(channel_values).astype(np.uint8)

    return rgb


def load_font(size, bold=False, mono=False):
    if mono:
        candidates = [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\cour.ttf"]
        if bold:
            candidates.insert(0, r"C:\Windows\Fonts\consolab.ttf")
    else:
        candidates = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\meiryo.ttc", r"C:\Windows\Fonts\msgothic.ttc"]
        if bold:
            candidates.insert(0, r"C:\Windows\Fonts\segoeuib.ttf")

    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_height(font, sample="Ag"):
    bbox = font.getbbox(sample)
    return bbox[3] - bbox[1]


def wrap_text_lines(draw, text, font, max_width):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_rotated_text(image, center, text, font, fill, angle):
    dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy)
    bbox = dummy_draw.textbbox((0, 0), text, font=font)
    text_image = Image.new("RGBA", (bbox[2] - bbox[0] + 8, bbox[3] - bbox[1] + 8), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_image)
    text_draw.text((4 - bbox[0], 4 - bbox[1]), text, font=font, fill=fill)
    rotated = text_image.rotate(angle, expand=True)
    image.alpha_composite(
        rotated,
        dest=(int(round(center[0] - rotated.width / 2.0)), int(round(center[1] - rotated.height / 2.0))),
    )


def build_colorbar_rgb(height, width, color_stops):
    bar = np.empty((height, width, 3), dtype=np.uint8)
    for row in range(height):
        value = 1.0 - row / max(height - 1, 1)
        bar[row, :, :] = np.array(interpolate_color(color_stops, value), dtype=np.uint8)
    return bar


def resize_for_display(image, target_size, prefer_crisp_upscale=False):
    if image.size == target_size:
        return image

    src_width, src_height = image.size
    dst_width, dst_height = target_size

    if dst_width < src_width or dst_height < src_height:
        # LANCZOS gives the cleanest result when many cells are compressed into fewer screen pixels.
        return image.resize(target_size, resample=Image.Resampling.LANCZOS)

    if prefer_crisp_upscale:
        return image.resize(target_size, resample=Image.Resampling.NEAREST)

    return image.resize(target_size, resample=Image.Resampling.BICUBIC)


def theta_for_index(index, count, value_min, value_max, reverse=False):
    if count <= 1:
        return 0.5 * (value_min + value_max)
    if reverse:
        index = count - 1 - index
    samples = build_theta_samples(value_min, value_max, count)
    return float(samples[index])


def build_theta_samples(value_min, value_max, count):
    if count <= 1:
        return np.array([0.5 * (value_min + value_max)], dtype=np.float64)
    span = value_max - value_min
    if abs(abs(span) - 360.0) < 1e-6:
        return np.linspace(value_min, value_max, count, endpoint=False, dtype=np.float64)
    return np.linspace(value_min, value_max, count, dtype=np.float64)


def format_tick_label(value):
    rounded = round(float(value))
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.1f}"


def build_axis_ticks(value_min, value_max, count=5):
    if count <= 1:
        return [(0.5 * (value_min + value_max), format_tick_label(0.5 * (value_min + value_max)))]
    return [(float(value), format_tick_label(value)) for value in np.linspace(value_min, value_max, count)]


def compute_extrema_info(values, theta1_min, theta1_max, theta2_min, theta2_max):
    finite = representative_finite_mask(values, theta1_min, theta1_max, theta2_min, theta2_max)
    if not finite.any():
        return {
            "max_point": None,
            "min_point": None,
            "lines": ["FTLE max: n/a", "FTLE min: n/a"],
        }

    finite_max = np.where(finite, values, -np.inf)
    finite_min = np.where(finite, values, np.inf)
    max_row, max_col = np.unravel_index(np.argmax(finite_max), values.shape)
    min_row, min_col = np.unravel_index(np.argmin(finite_min), values.shape)
    max_theta1 = theta_for_index(max_col, values.shape[1], theta1_min, theta1_max)
    max_theta2 = theta_for_index(max_row, values.shape[0], theta2_min, theta2_max, reverse=True)
    min_theta1 = theta_for_index(min_col, values.shape[1], theta1_min, theta1_max)
    min_theta2 = theta_for_index(min_row, values.shape[0], theta2_min, theta2_max, reverse=True)

    max_value = float(values[max_row, max_col])
    min_value = float(values[min_row, min_col])
    return {
        "max_point": {"theta1": max_theta1, "theta2": max_theta2, "ftle": max_value},
        "min_point": {"theta1": min_theta1, "theta2": min_theta2, "ftle": min_value},
        "lines": [
            f"FTLE max={max_value:.6g} at theta1={max_theta1:.3f} deg, theta2={max_theta2:.3f} deg",
            f"FTLE min={min_value:.6g} at theta1={min_theta1:.3f} deg, theta2={min_theta2:.3f} deg",
        ],
    }


def save_heatmap_png(file_path, values, theta1_min, theta1_max, theta2_min, theta2_max, info_lines, color_stops):
    file_path = resolve_output_path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    plot_rgb = build_heatmap_rgb(values, color_stops, theta1_min, theta1_max, theta2_min, theta2_max)
    grid = int(values.shape[0])
    vmin, vmax = value_range_for_heatmap(values, theta1_min, theta1_max, theta2_min, theta2_max)

    title_font = load_font(18, bold=True)
    subtitle_font = load_font(11)
    params_font = load_font(10)
    label_font = load_font(10, bold=True)
    tick_font = load_font(10, mono=True)

    left = 78
    right_pad = 112
    bar_gap = 26
    bar_width = 28
    bottom_pad = 78
    min_width = 640
    width = max(min_width, left + grid + bar_gap + bar_width + right_pad)

    probe_image = Image.new("RGBA", (width, 256), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe_image)
    text_width = width - 48
    title_lines = wrap_text_lines(probe_draw, "Chaos Map by Finite-Time Lyapunov Exponent", title_font, text_width)
    subtitle_lines = wrap_text_lines(
        probe_draw,
        "theta1-theta2 plane. Dark blue is regular-like, warm colors are more chaotic-like.",
        subtitle_font,
        text_width,
    )
    detail_lines = []
    for line in info_lines:
        detail_lines.extend(wrap_text_lines(probe_draw, line, params_font, text_width))

    top = (
        22
        + len(title_lines) * text_height(title_font)
        + 8
        + len(subtitle_lines) * text_height(subtitle_font)
        + 8
        + len(detail_lines) * text_height(params_font)
        + 26
    )
    height = top + grid + bottom_pad

    image = Image.new("RGBA", (width, height), (226, 232, 240, 255))
    draw = ImageDraw.Draw(image)

    y = 22
    for line in title_lines:
        draw.text((24, y), line, fill="#0f172a", font=title_font)
        y += text_height(title_font)
    y += 8
    for line in subtitle_lines:
        draw.text((24, y), line, fill="#334155", font=subtitle_font)
        y += text_height(subtitle_font)
    y += 8
    for line in detail_lines:
        draw.text((24, y), line, fill="#475569", font=params_font)
        y += text_height(params_font)

    plot_left = left
    plot_top = top
    plot_right = plot_left + grid
    plot_bottom = plot_top + grid

    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), fill="#f8fafc", outline="#cbd5e1")
    plot_image = Image.fromarray(plot_rgb, mode="RGB").convert("RGBA")
    image.alpha_composite(plot_image, dest=(plot_left, plot_top))
    draw.rectangle((plot_left, plot_top, plot_right, plot_bottom), outline="#cbd5e1")

    for angle_deg, label in build_axis_ticks(theta1_min, theta1_max):
        x = plot_left + (angle_deg - theta1_min) / max(theta1_max - theta1_min, 1e-12) * grid
        draw.line((x, plot_bottom, x, plot_bottom + 6), fill="#475569", width=1)
        draw.text((x, plot_bottom + 12), label, fill="#475569", font=tick_font, anchor="ma")
    for angle_deg, label in build_axis_ticks(theta2_min, theta2_max):
        y_tick = plot_top + (theta2_max - angle_deg) / max(theta2_max - theta2_min, 1e-12) * grid
        draw.line((plot_left - 6, y_tick, plot_left, y_tick), fill="#475569", width=1)
        draw.text((plot_left - 10, y_tick), label, fill="#475569", font=tick_font, anchor="rm")

    draw.text(((plot_left + plot_right) / 2.0, plot_bottom + 42), "theta1 (deg)", fill="#334155", font=label_font, anchor="mm")
    draw_rotated_text(
        image,
        (plot_left - 48, (plot_top + plot_bottom) / 2.0),
        "theta2 (deg)",
        label_font,
        "#334155",
        90,
    )

    bar_x0 = plot_right + bar_gap
    bar_y0 = plot_top
    bar_y1 = plot_bottom
    bar_image = Image.fromarray(build_colorbar_rgb(grid, bar_width, color_stops), mode="RGB").convert("RGBA")
    image.alpha_composite(bar_image, dest=(bar_x0, bar_y0))
    draw.rectangle((bar_x0, bar_y0, bar_x0 + bar_width, bar_y1), outline="#334155")
    draw.text((bar_x0 + bar_width / 2.0, bar_y0 - 18), "FTLE", fill="#334155", font=label_font, anchor="mm")
    draw.text((bar_x0 + bar_width + 12, bar_y0), f"{vmax:.3f}", fill="#475569", font=tick_font, anchor="la")
    draw.text((bar_x0 + bar_width + 12, bar_y1), f"{vmin:.3f}", fill="#475569", font=tick_font, anchor="ld")

    image.convert("RGB").save(file_path, format="PNG")
    return file_path

def compute_cell_batch(cell_range, params):
    start, stop = cell_range
    grid = params["grid"]
    theta1_values = params["theta1_values"]
    theta2_values = params["theta2_values"]
    indices = np.arange(start, stop, dtype=np.int32)
    rows = indices // grid
    cols = indices % grid

    started_at = time.perf_counter()
    values = finite_time_lyapunov_batch(
        theta1_deg=theta1_values[cols],
        theta2_deg=theta2_values[grid - 1 - rows],
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
    worker_seconds = max(time.perf_counter() - started_at, 1e-6)
    return rows, cols, values, worker_seconds


def show_chaos_map(duration, dt, auto_close_ms=0):
    root = tk.Tk()
    root.title("Double Pendulum Chaos Map")
    root.geometry("1180x860")
    root.minsize(920, 700)

    controls = tk.Frame(root, bg="#cbd5e1", padx=12, pady=10)
    controls.pack(fill="x")
    fields_frame = tk.Frame(controls, bg="#cbd5e1")
    fields_frame.pack(fill="x")
    actions_frame = tk.Frame(controls, bg="#cbd5e1")
    actions_frame.pack(fill="x", pady=(8, 0))
    canvas = tk.Canvas(root, bg="#e2e8f0", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    vars_map = {
        "m1": tk.StringVar(value="1.0"),
        "m2": tk.StringVar(value="1.0"),
        "l1": tk.StringVar(value="1.0"),
        "l2": tk.StringVar(value="1.0"),
        "omega1": tk.StringVar(value="0.0"),
        "omega2": tk.StringVar(value="0.0"),
        "grid": tk.StringVar(value="180"),
        "duration": tk.StringVar(value=f"{duration:.3g}"),
        "dt": tk.StringVar(value=f"{dt:.3g}"),
        "area_start_theta1": tk.StringVar(value=""),
        "area_start_theta2": tk.StringVar(value=""),
        "area_end_theta1": tk.StringVar(value=""),
        "area_end_theta2": tk.StringVar(value=""),
        "area_instruction": tk.StringVar(value="Press 'Select Area' and click two points on the plot."),
        "square_area_mode": tk.BooleanVar(value=True),
    }

    state = {
        "generation": 0,
        "grid": 0,
        "values": np.empty((0, 0), dtype=float),
        "running": False,
        "job": None,
        "executor": None,
        "futures": {},
        "completed_future_queue": queue.SimpleQueue(),
        "next_cell_index": 0,
        "total_cells": 0,
        "completed_cells": 0,
        "params_text": "",
        "extrema_lines": [],
        "max_point": None,
        "min_point": None,
        "picked_point": None,
        "pick_simulator_mode": False,
        "elapsed_seconds": 0.0,
        "run_started_at": None,
        "duration": duration,
        "dt": dt,
        "theta1_min": -180.0,
        "theta1_max": 180.0,
        "theta2_min": -180.0,
        "theta2_max": 180.0,
        "plot_bounds": None,
        "selection_mode": False,
        "selection_points": [],
        "selection_dialog": None,
        "save_dir": Path(__file__).resolve().parent / "docs" / "images",
        "save_filename": "chaos_heatmap.png",
        "worker_count": DEFAULT_WORKER_COUNT,
        "cells_per_task": DEFAULT_CELLS_PER_TASK,
        "max_in_flight": DEFAULT_MAX_IN_FLIGHT,
        "poll_interval_ms": DEFAULT_POLL_INTERVAL_MS,
        "task_runtime_ema": None,
        "resources": None,
        "heatmap_photo": None,
        "colorbar_photo": None,
        "last_redraw_at": 0.0,
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

    make_labeled_entry(fields_frame, "m1", vars_map["m1"])
    make_labeled_entry(fields_frame, "m2", vars_map["m2"])
    make_labeled_entry(fields_frame, "l1", vars_map["l1"])
    make_labeled_entry(fields_frame, "l2", vars_map["l2"])
    make_labeled_entry(fields_frame, "omega1", vars_map["omega1"])
    make_labeled_entry(fields_frame, "omega2", vars_map["omega2"])
    make_labeled_entry(fields_frame, "grid", vars_map["grid"], width=6)
    make_labeled_entry(fields_frame, "duration", vars_map["duration"], width=7)
    make_labeled_entry(fields_frame, "dt", vars_map["dt"], width=7)

    square_mode_check = tk.Checkbutton(
        fields_frame,
        text="Square Area",
        variable=vars_map["square_area_mode"],
        bg="#cbd5e1",
        fg="#0f172a",
        activebackground="#cbd5e1",
        activeforeground="#0f172a",
        selectcolor="#e2e8f0",
        font=("Yu Gothic UI", 10, "bold"),
        padx=6,
    )
    square_mode_check.pack(side="left", padx=(0, 10))

    status_var = tk.StringVar(value="Ready")
    status_label = tk.Label(
        fields_frame,
        textvariable=status_var,
        bg="#cbd5e1",
        fg="#334155",
        font=("Yu Gothic UI", 10),
        padx=12,
    )
    status_label.pack(side="right")

    action_buttons = []

    def layout_action_buttons(_event=None):
        if not action_buttons:
            return

        available_width = max(actions_frame.winfo_width(), actions_frame.winfo_reqwidth(), 1)
        button_width = max(button.winfo_reqwidth() for button in action_buttons) + 8
        columns = max(1, available_width // max(button_width, 1))

        for index, button in enumerate(action_buttons):
            row = index // columns
            column = index % columns
            button.grid(row=row, column=column, padx=(0, 8), pady=(0, 8), sticky="w")

    actions_frame.bind("<Configure>", layout_action_buttons)

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
        dialog = state["selection_dialog"]
        state["selection_dialog"] = None
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
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
        if value < 8 or value > 3600:
            raise ValueError("grid must be between 8 and 3600.")
        return value

    def value_range():
        return value_range_for_heatmap(
            state["values"],
            state["theta1_min"],
            state["theta1_max"],
            state["theta2_min"],
            state["theta2_max"],
        )

    def format_angle_text(value):
        return f"{value:.3f}"

    def reset_selection_vars():
        vars_map["area_start_theta1"].set("")
        vars_map["area_start_theta2"].set("")
        vars_map["area_end_theta1"].set("")
        vars_map["area_end_theta2"].set("")

    def update_selection_vars():
        reset_selection_vars()
        if len(state["selection_points"]) >= 1:
            first = state["selection_points"][0]
            vars_map["area_start_theta1"].set(format_angle_text(first["theta1"]))
            vars_map["area_start_theta2"].set(format_angle_text(first["theta2"]))
        if len(state["selection_points"]) >= 2:
            last = state["selection_points"][1]
            vars_map["area_end_theta1"].set(format_angle_text(last["theta1"]))
            vars_map["area_end_theta2"].set(format_angle_text(last["theta2"]))

    def parse_area_point_from_vars():
        field_map = [
            ("Start theta1", "area_start_theta1"),
            ("Start theta2", "area_start_theta2"),
            ("End theta1", "area_end_theta1"),
            ("End theta2", "area_end_theta2"),
        ]
        parsed = {}
        for label, key in field_map:
            text = vars_map[key].get().strip()
            if not text:
                raise ValueError(f"{label} is empty.")
            value = float(text)
            if value < -180.0 or value > 180.0:
                raise ValueError(f"{label} must be between -180 and 180.")
            parsed[key] = value

        first = {
            "theta1": parsed["area_start_theta1"],
            "theta2": parsed["area_start_theta2"],
        }
        last = {
            "theta1": parsed["area_end_theta1"],
            "theta2": parsed["area_end_theta2"],
        }
        if abs(first["theta1"] - last["theta1"]) < 1e-12 or abs(first["theta2"] - last["theta2"]) < 1e-12:
            raise ValueError("Selected area needs non-zero width and height.")
        return first, last

    def apply_selection_from_vars():
        try:
            first, last = parse_area_point_from_vars()
        except ValueError as exc:
            status_var.set(str(exc))
            vars_map["area_instruction"].set(str(exc))
            return

        state["selection_points"] = [first, last]
        state["selection_mode"] = False
        vars_map["area_instruction"].set("Selection completed. Press 'Select Area' to choose again.")
        update_selection_vars()
        status_var.set("Area selection updated from dialog")
        redraw()

    def on_close_selection_dialog():
        state["selection_mode"] = False
        dialog = state["selection_dialog"]
        state["selection_dialog"] = None
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        vars_map["area_instruction"].set("Press 'Select Area' and click two points on the plot.")
        redraw()

    def is_selection_dialog_visible():
        dialog = state["selection_dialog"]
        return dialog is not None and dialog.winfo_exists()

    def ensure_selection_dialog():
        dialog = state["selection_dialog"]
        if dialog is not None and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            dialog.focus_force()
            return dialog

        dialog = tk.Toplevel(root)
        dialog.title("Selected Area")
        dialog.resizable(False, False)
        dialog.transient(root)
        dialog.protocol("WM_DELETE_WINDOW", on_close_selection_dialog)

        body = tk.Frame(dialog, padx=14, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            textvariable=vars_map["area_instruction"],
            anchor="w",
            justify="left",
            font=("Yu Gothic UI", 10),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

        labels = [
            ("Start theta1", "area_start_theta1"),
            ("Start theta2", "area_start_theta2"),
            ("End theta1", "area_end_theta1"),
            ("End theta2", "area_end_theta2"),
        ]
        for index, (label_text, key) in enumerate(labels):
            row = 1 + index // 2
            column = (index % 2) * 2
            tk.Label(body, text=label_text, anchor="w", font=("Yu Gothic UI", 10, "bold")).grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0, 8),
                pady=(0, 8),
            )
            entry = tk.Entry(
                body,
                textvariable=vars_map[key],
                width=12,
                justify="right",
                font=("Consolas", 11),
            )
            entry.grid(row=row, column=column + 1, sticky="w", padx=(0, 14), pady=(0, 8))

        tk.Button(
            body,
            text="Apply",
            command=apply_selection_from_vars,
            font=("Yu Gothic UI", 10),
            padx=12,
            pady=2,
        ).grid(row=3, column=2, sticky="e", pady=(4, 0), padx=(0, 8))

        tk.Button(
            body,
            text="Close",
            command=on_close_selection_dialog,
            font=("Yu Gothic UI", 10),
            padx=12,
            pady=2,
        ).grid(row=3, column=3, sticky="e", pady=(4, 0))

        state["selection_dialog"] = dialog
        return dialog

    def canvas_to_theta(x, y):
        bounds = state["plot_bounds"]
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            return None
        normalized_x = (x - left) / (right - left)
        normalized_y = (y - top) / (bottom - top)
        theta1 = state["theta1_min"] + normalized_x * (state["theta1_max"] - state["theta1_min"])
        theta2 = state["theta2_max"] - normalized_y * (state["theta2_max"] - state["theta2_min"])
        return theta1, theta2

    def theta_to_canvas(theta1, theta2):
        bounds = state["plot_bounds"]
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        x = left + (theta1 - state["theta1_min"]) / max(state["theta1_max"] - state["theta1_min"], 1e-12) * (right - left)
        y = top + (state["theta2_max"] - theta2) / max(state["theta2_max"] - state["theta2_min"], 1e-12) * (bottom - top)
        return x, y

    def parse_current_simulator_params():
        return {
            "theta1": None,
            "theta2": None,
            "omega1": parse_float("omega1"),
            "omega2": parse_float("omega2"),
            "m1": parse_positive_float("m1"),
            "m2": parse_positive_float("m2"),
            "l1": parse_positive_float("l1"),
            "l2": parse_positive_float("l2"),
            "dt": parse_positive_float("dt"),
            "duration": parse_positive_float("duration"),
        }

    def launch_double_pendulum(theta1, theta2):
        try:
            sim_params = parse_current_simulator_params()
        except ValueError as exc:
            status_var.set(str(exc))
            return

        simulator_path = Path(__file__).resolve().parent / "double_pendulum.py"
        command = [
            sys.executable,
            str(simulator_path),
            "--theta1",
            f"{theta1:.10g}",
            "--theta2",
            f"{theta2:.10g}",
            "--omega1",
            f"{sim_params['omega1']:.10g}",
            "--omega2",
            f"{sim_params['omega2']:.10g}",
            "--m1",
            f"{sim_params['m1']:.10g}",
            "--m2",
            f"{sim_params['m2']:.10g}",
            "--l1",
            f"{sim_params['l1']:.10g}",
            "--l2",
            f"{sim_params['l2']:.10g}",
            "--dt",
            f"{sim_params['dt']:.10g}",
            "--duration",
            f"{sim_params['duration']:.10g}",
        ]

        try:
            subprocess.Popen(command, cwd=str(simulator_path.parent))
        except Exception as exc:
            status_var.set(f"Failed to launch simulator: {exc}")
            return

        state["picked_point"] = {"theta1": theta1, "theta2": theta2}
        status_var.set(f"Launched simulator at theta1={theta1:.3f}, theta2={theta2:.3f}")
        redraw()

    def launch_extrema_point(kind):
        point = state["max_point"] if kind == "max" else state["min_point"]
        if point is None:
            status_var.set(f"No {kind} FTLE point available yet")
            return
        launch_double_pendulum(point["theta1"], point["theta2"])

    def start_pick_simulator_point():
        if is_selection_dialog_visible():
            on_close_selection_dialog()
        state["selection_mode"] = False
        state["selection_points"] = []
        state["pick_simulator_mode"] = True
        status_var.set("Simulator pick mode: click a point inside the plot")
        redraw()

    def constrain_square_point(first_point, theta1, theta2):
        dx = theta1 - first_point["theta1"]
        dy = theta2 - first_point["theta2"]
        sign_x = 1.0 if dx >= 0.0 else -1.0
        sign_y = 1.0 if dy >= 0.0 else -1.0
        side = max(abs(dx), abs(dy))

        max_x = state["theta1_max"] - first_point["theta1"] if sign_x > 0.0 else first_point["theta1"] - state["theta1_min"]
        max_y = state["theta2_max"] - first_point["theta2"] if sign_y > 0.0 else first_point["theta2"] - state["theta2_min"]
        side = min(side, max_x, max_y)

        return {
            "theta1": first_point["theta1"] + sign_x * side,
            "theta2": first_point["theta2"] + sign_y * side,
        }

    def start_area_selection():
        ensure_selection_dialog()
        state["pick_simulator_mode"] = False
        state["selection_mode"] = True
        state["selection_points"] = []
        reset_selection_vars()
        vars_map["area_instruction"].set("Click the first point on the plot.")
        status_var.set("Area selection: click the first point inside the plot")
        redraw()

    def handle_canvas_click(event):
        bounds = state["plot_bounds"]
        if bounds is None:
            if state["selection_mode"] or state["pick_simulator_mode"]:
                status_var.set("Plot is not ready yet")
            return

        left, top, right, bottom = bounds
        if not (left <= event.x <= right and top <= event.y <= bottom):
            if state["selection_mode"] or state["pick_simulator_mode"]:
                status_var.set("Click inside the heatmap plot area")
            return

        theta = canvas_to_theta(event.x, event.y)
        if theta is None:
            if state["selection_mode"] or state["pick_simulator_mode"]:
                status_var.set("Failed to read the clicked coordinate")
            return

        if state["pick_simulator_mode"] and not state["selection_mode"]:
            state["pick_simulator_mode"] = False
            launch_double_pendulum(theta[0], theta[1])
            return

        if not state["selection_mode"]:
            return

        point = {"theta1": theta[0], "theta2": theta[1]}
        if len(state["selection_points"]) == 0:
            state["selection_points"] = [point]
            vars_map["area_instruction"].set("Click the final point on the plot.")
            status_var.set("Area selection: click the final point inside the plot")
        else:
            if vars_map["square_area_mode"].get():
                point = constrain_square_point(state["selection_points"][0], point["theta1"], point["theta2"])
            state["selection_points"] = [state["selection_points"][0], point]
            state["selection_mode"] = False
            vars_map["area_instruction"].set("Selection completed. Press 'Select Area' to choose again.")
            status_var.set("Area selection completed")

        update_selection_vars()
        redraw()

    def build_benchmark_line():
        elapsed = max(state["elapsed_seconds"], 1e-9)
        completed = int(state["completed_cells"])
        total = int(state["total_cells"])
        cells_per_second = completed / elapsed if completed > 0 else 0.0
        integration_steps_per_cell = max(1, int(state["duration"] / state["dt"])) if state["dt"] > 0.0 else 0
        integration_steps_per_second = cells_per_second * integration_steps_per_cell
        cells_per_worker = cells_per_second / max(1, state["worker_count"])

        return (
            f"benchmark: {completed}/{total} cells in {state['elapsed_seconds']:.2f} s, "
            f"{cells_per_second:.1f} cells/s, {integration_steps_per_second:.3e} integration steps/s, "
            f"{cells_per_worker:.2f} cells/s/worker"
        )

    def build_info_lines():
        lines = []
        if state["params_text"]:
            lines.append(state["params_text"])
        lines.append(build_benchmark_line())
        lines.extend(state["extrema_lines"])
        return lines

    def refresh_extrema_lines():
        extrema = compute_extrema_info(
            state["values"],
            state["theta1_min"],
            state["theta1_max"],
            state["theta2_min"],
            state["theta2_max"],
        )
        state["max_point"] = extrema["max_point"]
        state["min_point"] = extrema["min_point"]
        state["extrema_lines"] = extrema["lines"]

    def refresh_params_text(params):
        resources = state["resources"] or {}
        logical = resources.get("logical_cores", "?")
        physical = resources.get("physical_cores", "?")
        memory_text = "?"
        if resources.get("available_memory") is not None:
            memory_text = f"{resources['available_memory'] / (1024 ** 3):.1f}GB"

        state["params_text"] = (
            f"m1={params['m1']:.3g}, m2={params['m2']:.3g}, l1={params['l1']:.3g}, l2={params['l2']:.3g}, "
            f"omega1={params['omega1']:.3g}, omega2={params['omega2']:.3g}, duration={params['duration']:.3g}, dt={params['dt']:.3g}, "
            f"cpu={physical}P/{logical}L, mem={memory_text}, workers={state['worker_count']}, batch={state['cells_per_task']}, "
            f"inflight={state['max_in_flight']}, poll={state['poll_interval_ms']}ms, "
            f"task~{(state['task_runtime_ema'] or 0.0):.2f}s"
        )

    def retune_scheduler(params):
        task_seconds = state["task_runtime_ema"]
        if task_seconds is None:
            return

        changed = False
        desired_cells = state["cells_per_task"]
        if task_seconds < AUTO_MIN_TASK_SECONDS or task_seconds > AUTO_MAX_TASK_SECONDS:
            desired_cells = round_cells_per_task(state["cells_per_task"] * AUTO_TARGET_TASK_SECONDS / max(task_seconds, 1e-6))

        if desired_cells != state["cells_per_task"]:
            state["cells_per_task"] = desired_cells
            changed = True

        desired_in_flight = state["worker_count"] * choose_in_flight_multiplier(task_seconds)
        remaining_cells = max(0, state["total_cells"] - state["next_cell_index"])
        if remaining_cells > 0:
            remaining_tasks = math.ceil(remaining_cells / max(1, state["cells_per_task"]))
            desired_in_flight = min(desired_in_flight, max(1, remaining_tasks))
        else:
            desired_in_flight = 0

        desired_in_flight = max(1, desired_in_flight) if state["completed_cells"] < state["total_cells"] else 0
        if desired_in_flight != state["max_in_flight"]:
            state["max_in_flight"] = desired_in_flight
            changed = True

        desired_poll_interval_ms = choose_poll_interval_ms(task_seconds)
        if desired_poll_interval_ms != state["poll_interval_ms"]:
            state["poll_interval_ms"] = desired_poll_interval_ms
            changed = True

        if changed:
            refresh_params_text(params)

    def save_current_png(show_status=True, prompt_for_directory=False):
        if state["grid"] <= 0 or not state["values"].size or not np.isfinite(state["values"]).any():
            if show_status:
                status_var.set("No heatmap data to save yet")
            return None

        save_dir = state["save_dir"]
        if prompt_for_directory:
            selected_dir = filedialog.askdirectory(
                parent=root,
                title="Select folder to save PNG",
                initialdir=str(save_dir),
                mustexist=False,
            )
            if not selected_dir:
                if show_status:
                    status_var.set("Save canceled")
                return None
            save_dir = Path(selected_dir)
            state["save_dir"] = save_dir

        try:
            save_heatmap_png(
                file_path=save_dir / state["save_filename"],
                values=state["values"],
                theta1_min=state["theta1_min"],
                theta1_max=state["theta1_max"],
                theta2_min=state["theta2_min"],
                theta2_max=state["theta2_max"],
                info_lines=build_info_lines(),
                color_stops=color_stops,
            )
        except Exception as exc:
            if show_status:
                status_var.set(f"Save failed: {exc}")
            return None

        if show_status:
            status_var.set(f"Saved PNG (plot {state['grid']}x{state['grid']})")
        return True

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
        info_lines = build_info_lines()
        info_y = 68
        for index, line in enumerate(info_lines):
            canvas.create_text(
                24,
                info_y + index * 18,
                anchor="nw",
                text=line,
                fill="#475569",
                font=("Yu Gothic UI", 10),
            )

        left = 70
        top = info_y + max(1, len(info_lines)) * 18 + 24
        bar_width = 28
        bar_gap = 26
        available_plot_width = max(1, width - left - 110 - bar_gap - bar_width)
        available_plot_height = max(1, height - top - 70)
        plot_size = max(1, min(available_plot_width, available_plot_height))
        plot_right = left + plot_size
        bottom = top + plot_size
        state["plot_bounds"] = (left, top, plot_right, bottom)

        canvas.create_rectangle(left, top, plot_right, bottom, fill="#f8fafc", outline="#cbd5e1")

        if state["grid"] > 0 and state["values"].size:
            vmin, vmax = value_range()
            heatmap_image = Image.fromarray(
                build_heatmap_rgb(
                    state["values"],
                    color_stops,
                    state["theta1_min"],
                    state["theta1_max"],
                    state["theta2_min"],
                    state["theta2_max"],
                ),
                mode="RGB",
            )
            heatmap_image = resize_for_display(
                heatmap_image,
                (plot_size, plot_size),
                prefer_crisp_upscale=True,
            )
            state["heatmap_photo"] = ImageTk.PhotoImage(heatmap_image)
            canvas.create_image(left, top, anchor="nw", image=state["heatmap_photo"])

            for angle_deg, label in build_axis_ticks(state["theta1_min"], state["theta1_max"]):
                x = left + (angle_deg - state["theta1_min"]) / max(state["theta1_max"] - state["theta1_min"], 1e-12) * plot_size
                canvas.create_line(x, bottom, x, bottom + 6, fill="#475569")
                canvas.create_text(x, bottom + 22, text=label, fill="#475569", font=("Consolas", 10))
            for angle_deg, label in build_axis_ticks(state["theta2_min"], state["theta2_max"]):
                y = top + (state["theta2_max"] - angle_deg) / max(state["theta2_max"] - state["theta2_min"], 1e-12) * plot_size
                canvas.create_line(left - 6, y, left, y, fill="#475569")
                canvas.create_text(left - 10, y, text=label, anchor="e", fill="#475569", font=("Consolas", 10))

            canvas.create_text((left + plot_right) / 2.0, bottom + 42, text="theta1 (deg)", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
            canvas.create_text(left - 42, (top + bottom) / 2.0, text="theta2 (deg)", angle=90, fill="#334155", font=("Yu Gothic UI", 10, "bold"))

            bar_x0 = plot_right + bar_gap
            bar_y0 = top
            bar_y1 = bottom
            colorbar_image = Image.fromarray(build_colorbar_rgb(plot_size, bar_width, color_stops), mode="RGB")
            colorbar_image = resize_for_display(colorbar_image, (bar_width, plot_size))
            state["colorbar_photo"] = ImageTk.PhotoImage(colorbar_image)
            canvas.create_image(bar_x0, bar_y0, anchor="nw", image=state["colorbar_photo"])
            canvas.create_rectangle(bar_x0, bar_y0, bar_x0 + bar_width, bar_y1, outline="#334155")
            canvas.create_text(bar_x0 + bar_width / 2.0, bar_y0 - 18, text="FTLE", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
            canvas.create_text(bar_x0 + bar_width + 12, bar_y0, anchor="w", text=f"{vmax:.3f}", fill="#475569", font=("Consolas", 10))
            canvas.create_text(bar_x0 + bar_width + 12, bar_y1, anchor="w", text=f"{vmin:.3f}", fill="#475569", font=("Consolas", 10))
        else:
            state["heatmap_photo"] = None
            state["colorbar_photo"] = None

        if is_selection_dialog_visible():
            selection_styles = [
                ("Start", "#22c55e"),
                ("End", "#ef4444"),
            ]
            for index, point in enumerate(state["selection_points"][:2]):
                canvas_point = theta_to_canvas(point["theta1"], point["theta2"])
                if canvas_point is None:
                    continue
                x, y = canvas_point
                label, color = selection_styles[index]
                canvas.create_line(x, top, x, bottom, fill=color, dash=(6, 4), width=2)
                canvas.create_line(left, y, plot_right, y, fill=color, dash=(6, 4), width=2)
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color, outline="white", width=1)
                canvas.create_text(
                    x + 8,
                    y - 8,
                    anchor="sw",
                    text=label,
                    fill=color,
                    font=("Yu Gothic UI", 10, "bold"),
                )

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
            and len(state["futures"]) < state["max_in_flight"]
            and state["next_cell_index"] < state["total_cells"]
        ):
            start = state["next_cell_index"]
            stop = min(start + state["cells_per_task"], state["total_cells"])
            state["next_cell_index"] = stop
            cell_range = (start, stop)
            future = state["executor"].submit(compute_cell_batch, cell_range, params)
            future.add_done_callback(
                lambda done_future, done_generation=generation: state["completed_future_queue"].put((done_generation, done_future))
            )
            state["futures"][future] = {
                "batch_size": stop - start,
            }

    def poll_results(generation, params):
        if generation != state["generation"] or not state["running"]:
            return

        total_cells = state["total_cells"]
        if state["run_started_at"] is not None:
            state["elapsed_seconds"] = max(0.0, time.perf_counter() - state["run_started_at"])
        finished = []
        while True:
            try:
                done_generation, future = state["completed_future_queue"].get_nowait()
            except queue.Empty:
                break
            if done_generation != generation or future not in state["futures"]:
                continue
            finished.append(future)

        for future in finished:
            metadata = state["futures"].pop(future)
            batch_size = metadata["batch_size"]
            try:
                rows, cols, values, worker_seconds = future.result()
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
            if state["task_runtime_ema"] is None:
                state["task_runtime_ema"] = worker_seconds
            else:
                state["task_runtime_ema"] = 0.25 * worker_seconds + 0.75 * state["task_runtime_ema"]

        if finished:
            refresh_extrema_lines()
            retune_scheduler(params)
            status_var.set(f"Calculating {state['completed_cells']}/{total_cells} cells")
            now = time.perf_counter()
            if now - state["last_redraw_at"] >= 0.15:
                redraw()
                root.update_idletasks()
                state["last_redraw_at"] = now

        if state["completed_cells"] >= total_cells:
            state["running"] = False
            if state["run_started_at"] is not None:
                state["elapsed_seconds"] = max(0.0, time.perf_counter() - state["run_started_at"])
            shutdown_executor()
            compute_button.config(state="normal")
            stop_button.config(state="disabled")
            saved = save_current_png(show_status=False)
            if saved:
                status_var.set(f"Done and saved PNG (plot {state['grid']}x{state['grid']})")
            else:
                status_var.set("Done")
            redraw()
            state["last_redraw_at"] = time.perf_counter()
            return

        submit_tasks(generation, params)
        state["job"] = root.after(state["poll_interval_ms"], lambda: poll_results(generation, params))

    def stop_compute():
        if not state["running"]:
            return

        state["generation"] += 1
        state["running"] = False
        if state["run_started_at"] is not None:
            state["elapsed_seconds"] = max(0.0, time.perf_counter() - state["run_started_at"])
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
        state["completed_future_queue"] = queue.SimpleQueue()
        state["next_cell_index"] = 0
        state["total_cells"] = grid * grid
        state["completed_cells"] = 0
        state["last_redraw_at"] = 0.0
        state["task_runtime_ema"] = None
        state["extrema_lines"] = []
        state["max_point"] = None
        state["min_point"] = None
        state["elapsed_seconds"] = 0.0
        state["run_started_at"] = time.perf_counter()
        state["duration"] = params["duration"]
        state["dt"] = params["dt"]
        if len(state["selection_points"]) >= 2:
            first, last = state["selection_points"][:2]
            state["theta1_min"] = min(first["theta1"], last["theta1"])
            state["theta1_max"] = max(first["theta1"], last["theta1"])
            state["theta2_min"] = min(first["theta2"], last["theta2"])
            state["theta2_max"] = max(first["theta2"], last["theta2"])
        else:
            state["theta1_min"] = -180.0
            state["theta1_max"] = 180.0
            state["theta2_min"] = -180.0
            state["theta2_max"] = 180.0
        params["grid"] = grid
        params["theta1_values"] = build_theta_samples(state["theta1_min"], state["theta1_max"], grid)
        params["theta2_values"] = build_theta_samples(state["theta2_min"], state["theta2_max"], grid)
        status_var.set("Auto tuning workload...")
        redraw()
        root.update_idletasks()
        tuning = choose_auto_execution_settings(params)
        state["resources"] = tuning["resources"]
        state["worker_count"] = tuning["worker_count"]
        state["cells_per_task"] = tuning["cells_per_task"]
        state["max_in_flight"] = tuning["max_in_flight"]
        state["poll_interval_ms"] = tuning["poll_interval_ms"]
        state["executor"] = cf.ProcessPoolExecutor(
            max_workers=state["worker_count"],
            mp_context=mp.get_context("spawn"),
        )
        refresh_params_text(params)
        state["save_filename"] = build_save_filename(params)
        status_var.set(f"Calculating 0/{grid * grid} cells")
        compute_button.config(state="disabled")
        stop_button.config(state="normal")
        redraw()
        root.update_idletasks()
        submit_tasks(state["generation"], params)
        state["job"] = root.after(state["poll_interval_ms"], lambda: poll_results(state["generation"], params))

    compute_button = tk.Button(
        actions_frame,
        text="Compute Heatmap",
        command=start_compute,
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(compute_button)

    stop_button = tk.Button(
        actions_frame,
        text="Stop",
        command=stop_compute,
        bg="#ef4444",
        fg="white",
        activebackground="#dc2626",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
        state="disabled",
    )
    action_buttons.append(stop_button)

    save_button = tk.Button(
        actions_frame,
        text="Save Current",
        command=lambda: save_current_png(prompt_for_directory=True),
        bg="#0f766e",
        fg="white",
        activebackground="#115e59",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(save_button)

    area_button = tk.Button(
        actions_frame,
        text="Select Area",
        command=start_area_selection,
        bg="#7c3aed",
        fg="white",
        activebackground="#6d28d9",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(area_button)

    max_sim_button = tk.Button(
        actions_frame,
        text="Open Max Sim",
        command=lambda: launch_extrema_point("max"),
        bg="#b45309",
        fg="white",
        activebackground="#92400e",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(max_sim_button)

    min_sim_button = tk.Button(
        actions_frame,
        text="Open Min Sim",
        command=lambda: launch_extrema_point("min"),
        bg="#0f766e",
        fg="white",
        activebackground="#115e59",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(min_sim_button)

    pick_sim_button = tk.Button(
        actions_frame,
        text="Pick Sim Point",
        command=start_pick_simulator_point,
        bg="#1d4ed8",
        fg="white",
        activebackground="#1e40af",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        width=16,
        pady=4,
    )
    action_buttons.append(pick_sim_button)

    layout_action_buttons()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.bind("<Configure>", redraw)
    root.bind("<KeyPress-q>", lambda _event: close_window())
    root.bind("<Escape>", lambda _event: close_window())
    canvas.bind("<Button-1>", handle_canvas_click)
    root.after(0, start_compute)
    root.focus_force()

    if auto_close_ms > 0:
        root.after(auto_close_ms, root.destroy)

    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Show a theta1-theta2 chaos heatmap for a double pendulum.")
    parser.add_argument("--duration", type=float, default=10.0, help="integration time for each grid cell")
    parser.add_argument("--dt", type=float, default=0.02, help="time step")
    parser.add_argument("--auto-close-ms", type=int, default=0, help="auto close the window after N milliseconds")
    return parser.parse_args()


if __name__ == "__main__":
    mp.freeze_support()
    args = parse_args()
    show_chaos_map(duration=args.duration, dt=args.dt, auto_close_ms=args.auto_close_ms)
