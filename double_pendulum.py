import argparse
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


def derivatives(state, m1, m2, l1, l2, g):
    theta1, omega1, theta2, omega2 = state
    delta = theta2 - theta1

    den1 = (m1 + m2) * l1 - m2 * l1 * math.cos(delta) ** 2
    den2 = (l2 / l1) * den1

    dtheta1 = omega1
    dtheta2 = omega2

    domega1 = (
        m2 * l1 * omega1**2 * math.sin(delta) * math.cos(delta)
        + m2 * g * math.sin(theta2) * math.cos(delta)
        + m2 * l2 * omega2**2 * math.sin(delta)
        - (m1 + m2) * g * math.sin(theta1)
    ) / den1

    domega2 = (
        -m2 * l2 * omega2**2 * math.sin(delta) * math.cos(delta)
        + (m1 + m2)
        * (
            g * math.sin(theta1) * math.cos(delta)
            - l1 * omega1**2 * math.sin(delta)
            - g * math.sin(theta2)
        )
    ) / den2

    return np.array([dtheta1, domega1, dtheta2, domega2], dtype=float)


def rk4_step(state, dt, m1, m2, l1, l2, g):
    k1 = derivatives(state, m1, m2, l1, l2, g)
    k2 = derivatives(state + 0.5 * dt * k1, m1, m2, l1, l2, g)
    k3 = derivatives(state + 0.5 * dt * k2, m1, m2, l1, l2, g)
    k4 = derivatives(state + dt * k3, m1, m2, l1, l2, g)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def simulate(
    theta1_deg=120.0,
    theta2_deg=-10.0,
    omega1=0.0,
    omega2=0.0,
    m1=1,
    m2=1,
    l1=1,
    l2=1,
    g=9.81,
    dt=0.01,
    duration=100.0,
):
    steps = max(1, int(duration / dt))
    state = np.array(
        [math.radians(theta1_deg), omega1, math.radians(theta2_deg), omega2],
        dtype=float,
    )

    states = np.zeros((steps, 4), dtype=float)
    for index in range(steps):
        states[index] = state
        state = rk4_step(state, dt, m1, m2, l1, l2, g)

    theta1 = states[:, 0]
    theta2 = states[:, 2]

    x1 = l1 * np.sin(theta1)
    y1 = -l1 * np.cos(theta1)
    x2 = x1 + l2 * np.sin(theta2)
    y2 = y1 - l2 * np.cos(theta2)
    return x1, y1, x2, y2


def build_playback_schedule(x2, y2, dt, target_fps, min_fps, max_fps):
    total_frames = len(x2)
    if total_frames <= 1:
        return [0], []

    segment_distance = np.hypot(np.diff(x2), np.diff(y2))
    total_distance = float(np.sum(segment_distance))
    total_duration = max((total_frames - 1) * dt, dt)

    target_frame_count = max(1, int(round(total_duration * max(target_fps, 1.0))))
    target_distance = (total_distance / target_frame_count) * 0.25 if total_distance > 0.0 else 0.0
    min_interval = 1.0 / max(max_fps, 1.0)
    max_interval = 1.0 / max(min_fps, 0.1)

    playback_frames = [0]
    playback_delays_ms = []
    current = 0

    while current < total_frames - 1:
        next_frame = current + 1
        elapsed_time = dt
        accumulated_distance = float(segment_distance[current]) if current < len(segment_distance) else 0.0

        while next_frame < total_frames - 1:
            reached_min_interval = elapsed_time >= min_interval
            reached_target_distance = accumulated_distance >= target_distance
            reached_max_interval = elapsed_time >= max_interval

            if reached_max_interval or (reached_min_interval and reached_target_distance):
                break

            accumulated_distance += float(segment_distance[next_frame])
            next_frame += 1
            elapsed_time += dt

        playback_frames.append(next_frame)
        playback_delays_ms.append(max(1, int(round((next_frame - current) * dt * 1000.0))))
        current = next_frame

    return playback_frames, playback_delays_ms


def compute_reach(x1, y1, x2, y2):
    return float(np.max(np.abs(np.concatenate([x1, y1, x2, y2])))) + 0.25


def world_to_screen(px, py, width, height, reach, margin=70):
    scale = min(
        (width - 2 * margin) / max(2 * reach, 1e-12),
        (height - 2 * margin) / max(2 * reach, 1e-12),
    )
    sx = width / 2 + px * scale
    sy = height / 2 - py * scale
    return int(round(sx)), int(round(sy))


def build_video_frame_indices(total_frames, dt, fps):
    if total_frames <= 1:
        return np.array([0], dtype=np.int32)

    fps = max(float(fps), 1.0)
    total_duration = max((total_frames - 1) * dt, 0.0)
    times = np.arange(0.0, total_duration + (0.5 / fps), 1.0 / fps, dtype=np.float64)
    indices = np.clip(np.rint(times / dt).astype(np.int32), 0, total_frames - 1)
    if indices.size == 0 or indices[-1] != total_frames - 1:
        indices = np.append(indices, total_frames - 1)
    return np.unique(indices)


def make_default_mp4_name(params):
    def token(value):
        return f"{float(value):.6g}".replace("-", "m").replace(".", "p")

    return (
        "double_pendulum"
        f"_t1-{token(params['theta1_deg'])}"
        f"_t2-{token(params['theta2_deg'])}"
        f"_o1-{token(params['omega1'])}"
        f"_o2-{token(params['omega2'])}"
        f"_m1-{token(params['m1'])}"
        f"_m2-{token(params['m2'])}"
        f"_l1-{token(params['l1'])}"
        f"_l2-{token(params['l2'])}"
        f"_dur-{token(params['duration'])}"
        f"_dt-{token(params['dt'])}.mp4"
    )


def save_simulation_mp4(
    file_path,
    x1,
    y1,
    x2,
    y2,
    dt,
    fps,
    width=1280,
    height=960,
    subtitle="",
):
    if cv2 is None:
        raise RuntimeError("OpenCV is not available, so MP4 export cannot be used.")

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    frame_indices = build_video_frame_indices(len(x1), dt, fps)
    reach = compute_reach(x1, y1, x2, y2)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        max(float(fps), 1.0),
        (int(width), int(height)),
    )
    if not writer.isOpened():
        raise RuntimeError("Failed to open MP4 writer.")

    trace_points = []
    try:
        for frame in frame_indices:
            image = np.full((height, width, 3), 255, dtype=np.uint8)

            center_x = width // 2
            center_y = height // 2
            cv2.line(image, (0, center_y), (width, center_y), (229, 231, 235), 1, cv2.LINE_AA)
            cv2.line(image, (center_x, 0), (center_x, height), (229, 231, 235), 1, cv2.LINE_AA)

            origin = world_to_screen(0.0, 0.0, width, height, reach)
            bob1 = world_to_screen(float(x1[frame]), float(y1[frame]), width, height, reach)
            bob2 = world_to_screen(float(x2[frame]), float(y2[frame]), width, height, reach)
            trace_points.append(bob2)

            if len(trace_points) >= 2:
                cv2.polylines(
                    image,
                    [np.array(trace_points, dtype=np.int32)],
                    False,
                    (74, 163, 22),
                    2,
                    cv2.LINE_AA,
                )

            cv2.line(image, origin, bob1, (235, 99, 37), 3, cv2.LINE_AA)
            cv2.line(image, bob1, bob2, (37, 99, 235), 3, cv2.LINE_AA)
            cv2.circle(image, origin, 5, (17, 24, 39), -1, cv2.LINE_AA)
            cv2.circle(image, bob1, 10, (22, 115, 249), -1, cv2.LINE_AA)
            cv2.circle(image, bob2, 10, (38, 38, 220), -1, cv2.LINE_AA)

            cv2.putText(image, "Double Pendulum", (20, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (17, 24, 39), 2, cv2.LINE_AA)
            cv2.putText(
                image,
                f"t = {frame * dt:6.3f} s",
                (20, 66),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (31, 41, 55),
                2,
                cv2.LINE_AA,
            )
            if subtitle:
                cv2.putText(
                    image,
                    subtitle,
                    (20, 98),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.58,
                    (71, 85, 105),
                    1,
                    cv2.LINE_AA,
                )

            writer.write(image)
    finally:
        writer.release()


def animate_pendulum(
    theta1_deg=120.0,
    theta2_deg=-10.0,
    omega1=0.0,
    omega2=0.0,
    m1=1.0,
    m2=1.0,
    l1=1.0,
    l2=1.0,
    g=9.81,
    dt=0.01,
    duration=100.0,
    keep_open=True,
    target_fps=30.0,
    min_fps=10.0,
    max_fps=120.0,
):
    root = tk.Tk()
    root.title("Double Pendulum")
    root.geometry("980x820")
    root.minsize(700, 600)
    root.resizable(True, True)

    controls = tk.Frame(root, bg="#e5e7eb", padx=12, pady=10)
    controls.pack(fill="x")
    fields_frame = tk.Frame(controls, bg="#e5e7eb")
    fields_frame.pack(fill="x")
    actions_frame = tk.Frame(controls, bg="#e5e7eb")
    actions_frame.pack(fill="x", pady=(4, 0))
    canvas = tk.Canvas(root, bg="white", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    trace_chunk_points = 64
    vars_map = {
        "theta1": tk.StringVar(value=f"{theta1_deg:.6g}"),
        "theta2": tk.StringVar(value=f"{theta2_deg:.6g}"),
        "omega1": tk.StringVar(value=f"{omega1:.6g}"),
        "omega2": tk.StringVar(value=f"{omega2:.6g}"),
        "m1": tk.StringVar(value=f"{m1:.6g}"),
        "m2": tk.StringVar(value=f"{m2:.6g}"),
        "l1": tk.StringVar(value=f"{l1:.6g}"),
        "l2": tk.StringVar(value=f"{l2:.6g}"),
        "g": tk.StringVar(value=f"{g:.6g}"),
        "dt": tk.StringVar(value=f"{dt:.6g}"),
        "duration": tk.StringVar(value=f"{duration:.6g}"),
    }
    status_var = tk.StringVar(value="Ready")

    state = {
        "x1": np.array([], dtype=float),
        "y1": np.array([], dtype=float),
        "x2": np.array([], dtype=float),
        "y2": np.array([], dtype=float),
        "dt": dt,
        "duration": duration,
        "total_frames": 0,
        "playback_frames": [0],
        "playback_delays_ms": [],
        "reach": 1.25,
        "frame": 0,
        "playback_index": 0,
        "job": None,
        "running": True,
        "finished": False,
        "trace_frame": 0,
        "resize_job": None,
        "viewport_width": 900,
        "viewport_height": 760,
    }
    items = {}
    trace_state = {
        "items": [],
        "last_screen": None,
        "current_item": None,
        "current_coords": [],
    }
    action_buttons = []

    def make_labeled_entry(parent, label, variable, width=8):
        frame = tk.Frame(parent, bg="#e5e7eb")
        frame.pack(side="left", padx=(0, 10), pady=(0, 6))
        tk.Label(frame, text=label, bg="#e5e7eb", fg="#111827", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
        entry = tk.Entry(frame, textvariable=variable, width=width, font=("Consolas", 11))
        entry.pack()
        entry.bind("<Return>", lambda _event: start_simulation())
        return entry

    for label, key in [
        ("theta1", "theta1"),
        ("theta2", "theta2"),
        ("omega1", "omega1"),
        ("omega2", "omega2"),
        ("m1", "m1"),
        ("m2", "m2"),
        ("l1", "l1"),
        ("l2", "l2"),
        ("g", "g"),
        ("dt", "dt"),
        ("duration", "duration"),
    ]:
        make_labeled_entry(fields_frame, label, vars_map[key], width=8 if key != "duration" else 9)

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

    start_button = tk.Button(
        actions_frame,
        text="Start",
        font=("Yu Gothic UI", 10, "bold"),
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        padx=14,
        pady=3,
    )
    action_buttons.append(start_button)

    save_mp4_button = tk.Button(
        actions_frame,
        text="Save MP4",
        font=("Yu Gothic UI", 10, "bold"),
        bg="#0f766e",
        fg="white",
        activebackground="#115e59",
        activeforeground="white",
        padx=14,
        pady=3,
    )
    action_buttons.append(save_mp4_button)

    status_label = tk.Label(
        fields_frame,
        textvariable=status_var,
        bg="#e5e7eb",
        fg="#374151",
        font=("Yu Gothic UI", 10),
    )
    status_label.pack(side="left", pady=(0, 6))

    def close_window(_event=None):
        if not state["running"]:
            return
        state["running"] = False
        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None
        if state["resize_job"] is not None:
            root.after_cancel(state["resize_job"])
            state["resize_job"] = None
        root.destroy()

    root.bind("<KeyPress-q>", close_window)
    root.bind("<Escape>", close_window)
    root.update_idletasks()
    state["viewport_width"] = max(canvas.winfo_width(), 1)
    state["viewport_height"] = max(canvas.winfo_height(), 1)

    def world_to_screen(px, py):
        margin = 70
        scale = min(
            (state["viewport_width"] - 2 * margin) / (2 * state["reach"]),
            (state["viewport_height"] - 2 * margin) / (2 * state["reach"]),
        )
        sx = state["viewport_width"] / 2 + px * scale
        sy = state["viewport_height"] / 2 - py * scale
        return sx, sy

    def set_circle(item_id, cx, cy, radius):
        canvas.coords(item_id, cx - radius, cy - radius, cx + radius, cy + radius)

    def clear_trace():
        for item_id in trace_state["items"]:
            canvas.delete(item_id)
        trace_state["items"].clear()
        trace_state["last_screen"] = None
        trace_state["current_item"] = None
        trace_state["current_coords"] = []

    def append_trace_until(frame):
        if trace_state["last_screen"] is None:
            trace_state["last_screen"] = world_to_screen(float(state["x2"][0]), float(state["y2"][0]))

        if frame <= state["trace_frame"]:
            return

        for index in range(state["trace_frame"] + 1, frame + 1):
            sx, sy = world_to_screen(float(state["x2"][index]), float(state["y2"][index]))
            last_x, last_y = trace_state["last_screen"]

            if trace_state["current_item"] is None:
                coords = [last_x, last_y, sx, sy]
                trace_state["current_item"] = canvas.create_line(
                    *coords,
                    fill="#16a34a",
                    width=2,
                )
                trace_state["items"].append(trace_state["current_item"])
                canvas.tag_lower(trace_state["current_item"], items["rod"])
                trace_state["current_coords"] = coords
            else:
                trace_state["current_coords"].extend([sx, sy])
                canvas.coords(trace_state["current_item"], *trace_state["current_coords"])

            trace_state["last_screen"] = (sx, sy)
            state["trace_frame"] = index

            if len(trace_state["current_coords"]) >= trace_chunk_points * 2:
                trace_state["current_item"] = None
                trace_state["current_coords"] = []

    def update_scene():
        frame = state["frame"]
        ox, oy = world_to_screen(0.0, 0.0)
        p1x, p1y = world_to_screen(float(state["x1"][frame]), float(state["y1"][frame]))
        p2x, p2y = world_to_screen(float(state["x2"][frame]), float(state["y2"][frame]))

        canvas.itemconfigure(items["time"], text=f"t = {frame * state['dt']:5.2f} s")
        canvas.coords(items["x_axis"], 0, state["viewport_height"] / 2, state["viewport_width"], state["viewport_height"] / 2)
        canvas.coords(items["y_axis"], state["viewport_width"] / 2, 0, state["viewport_width"] / 2, state["viewport_height"])
        canvas.coords(items["rod"], ox, oy, p1x, p1y, p2x, p2y)
        set_circle(items["origin"], ox, oy, 5)
        set_circle(items["bob1"], p1x, p1y, 10)
        set_circle(items["bob2"], p2x, p2y, 10)

    def schedule_next_step():
        if len(state["playback_frames"]) <= 1 or not state["running"] or state["finished"]:
            return
        if not (1 <= state["playback_index"] < len(state["playback_frames"])):
            return
        delay_index = state["playback_index"] - 1
        if delay_index >= len(state["playback_delays_ms"]):
            return
        delay_ms = state["playback_delays_ms"][delay_index]
        state["job"] = root.after(delay_ms, step)

    def restart_animation():
        state["resize_job"] = None
        if not state["running"]:
            return

        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None

        if state["total_frames"] <= 0:
            return

        state["frame"] = state["playback_frames"][0]
        state["playback_index"] = 1 if len(state["playback_frames"]) > 1 else 0
        state["finished"] = False
        state["trace_frame"] = 0
        clear_trace()
        trace_state["last_screen"] = world_to_screen(float(state["x2"][0]), float(state["y2"][0]))
        update_scene()
        schedule_next_step()

    def on_resize(event):
        new_width = max(event.width, 1)
        new_height = max(event.height, 1)
        if new_width == state["viewport_width"] and new_height == state["viewport_height"]:
            return

        state["viewport_width"] = new_width
        state["viewport_height"] = new_height
        if state["resize_job"] is not None:
            root.after_cancel(state["resize_job"])
        state["resize_job"] = root.after(120, restart_animation)

    def step():
        if not state["running"]:
            return

        if state["finished"]:
            return

        playback_index = state["playback_index"]
        if playback_index <= 0:
            playback_index = 1
            state["playback_index"] = playback_index
        if playback_index >= len(state["playback_frames"]):
            state["finished"] = True
            return

        frame = state["playback_frames"][playback_index]
        state["frame"] = frame
        append_trace_until(frame)
        update_scene()

        if playback_index >= len(state["playback_frames"]) - 1 or frame >= state["total_frames"] - 1:
            state["finished"] = True
            state["frame"] = state["total_frames"] - 1
            append_trace_until(state["total_frames"] - 1)
            update_scene()
            if not keep_open:
                state["job"] = root.after(300, close_window)
            return

        state["playback_index"] += 1
        schedule_next_step()

    def parse_float(name):
        return float(vars_map[name].get())

    def parse_positive_float(name):
        value = float(vars_map[name].get())
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
        return value

    def build_simulation_params():
        try:
            params = {
                "theta1_deg": parse_float("theta1"),
                "theta2_deg": parse_float("theta2"),
                "omega1": parse_float("omega1"),
                "omega2": parse_float("omega2"),
                "m1": parse_positive_float("m1"),
                "m2": parse_positive_float("m2"),
                "l1": parse_positive_float("l1"),
                "l2": parse_positive_float("l2"),
                "g": parse_positive_float("g"),
                "dt": parse_positive_float("dt"),
                "duration": parse_positive_float("duration"),
            }
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if params["duration"] < params["dt"]:
            raise ValueError("duration must be greater than or equal to dt.")
        return params

    def build_video_subtitle(params):
        return (
            f"theta1={params['theta1_deg']:.3f} deg, theta2={params['theta2_deg']:.3f} deg, "
            f"omega1={params['omega1']:.3f}, omega2={params['omega2']:.3f}, "
            f"m1={params['m1']:.3f}, m2={params['m2']:.3f}, "
            f"l1={params['l1']:.3f}, l2={params['l2']:.3f}"
        )

    def start_simulation():
        try:
            params = build_simulation_params()
        except ValueError as exc:
            status_var.set(str(exc))
            return

        try:
            x1_new, y1_new, x2_new, y2_new = simulate(**params)
        except Exception as exc:
            status_var.set(f"Simulation failed: {exc}")
            return

        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None

        state["x1"] = x1_new
        state["y1"] = y1_new
        state["x2"] = x2_new
        state["y2"] = y2_new
        state["dt"] = params["dt"]
        state["duration"] = params["duration"]
        state["total_frames"] = len(x1_new)
        state["playback_frames"], state["playback_delays_ms"] = build_playback_schedule(
            x2=x2_new,
            y2=y2_new,
            dt=params["dt"],
            target_fps=target_fps,
            min_fps=min_fps,
            max_fps=max_fps,
        )
        state["reach"] = compute_reach(x1_new, y1_new, x2_new, y2_new)
        state["frame"] = state["playback_frames"][0]
        state["playback_index"] = 1 if len(state["playback_frames"]) > 1 else 0
        state["finished"] = False
        state["trace_frame"] = 0
        clear_trace()
        trace_state["last_screen"] = world_to_screen(float(state["x2"][0]), float(state["y2"][0]))
        update_scene()
        schedule_next_step()
        status_var.set(
            f"Running: theta1={params['theta1_deg']:.3f}, theta2={params['theta2_deg']:.3f}, "
            f"duration={params['duration']:.3f}s, dt={params['dt']:.4g}"
        )

    def export_mp4():
        if cv2 is None:
            status_var.set("OpenCV is not available, so MP4 export cannot be used.")
            return

        try:
            params = build_simulation_params()
        except ValueError as exc:
            status_var.set(str(exc))
            return

        output_path = filedialog.asksaveasfilename(
            parent=root,
            title="Save MP4",
            initialdir=str(Path(__file__).resolve().parent),
            initialfile=make_default_mp4_name(params),
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
        )
        if not output_path:
            status_var.set("MP4 export cancelled")
            return

        status_var.set("Exporting MP4...")
        root.config(cursor="watch")
        root.update_idletasks()
        try:
            x1_new, y1_new, x2_new, y2_new = simulate(**params)
            save_simulation_mp4(
                output_path,
                x1_new,
                y1_new,
                x2_new,
                y2_new,
                dt=params["dt"],
                fps=target_fps,
                subtitle=build_video_subtitle(params),
            )
        except Exception as exc:
            status_var.set(f"MP4 export failed: {exc}")
            return
        finally:
            root.config(cursor="")
            root.update_idletasks()

        status_var.set(f"Saved MP4: {Path(output_path).name}")

    root.update_idletasks()
    items["title"] = canvas.create_text(
        18,
        18,
        anchor="nw",
        text="Double Pendulum",
        fill="#111827",
        font=("Yu Gothic UI", 18, "bold"),
    )
    items["help"] = canvas.create_text(
        18,
        48,
        anchor="nw",
        text="Press q or Esc to close",
        fill="#4b5563",
        font=("Yu Gothic UI", 11),
    )
    items["time"] = canvas.create_text(
        18,
        70,
        anchor="nw",
        text="t =  0.00 s",
        fill="#1f2937",
        font=("Consolas", 12),
    )
    items["x_axis"] = canvas.create_line(
        0,
        state["viewport_height"] / 2,
        state["viewport_width"],
        state["viewport_height"] / 2,
        fill="#e5e7eb",
    )
    items["y_axis"] = canvas.create_line(
        state["viewport_width"] / 2,
        0,
        state["viewport_width"] / 2,
        state["viewport_height"],
        fill="#e5e7eb",
    )
    items["rod"] = canvas.create_line(0, 0, 0, 0, 0, 0, fill="#2563eb", width=3)
    items["origin"] = canvas.create_oval(0, 0, 0, 0, fill="#111827", outline="")
    items["bob1"] = canvas.create_oval(0, 0, 0, 0, fill="#f97316", outline="")
    items["bob2"] = canvas.create_oval(0, 0, 0, 0, fill="#dc2626", outline="")
    canvas.bind("<Configure>", on_resize)
    start_button.configure(command=start_simulation)
    save_mp4_button.configure(command=export_mp4, state="normal" if cv2 is not None else "disabled")
    start_simulation()
    root.focus_force()
    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Animate a double pendulum.")
    parser.add_argument("--theta1", type=float, default=120.0, help="first angle in degrees")
    parser.add_argument("--theta2", type=float, default=-10.0, help="second angle in degrees")
    parser.add_argument("--omega1", type=float, default=0.0, help="first angular velocity")
    parser.add_argument("--omega2", type=float, default=0.0, help="second angular velocity")
    parser.add_argument("--m1", type=float, default=1.0, help="first mass")
    parser.add_argument("--m2", type=float, default=1.0, help="second mass")
    parser.add_argument("--l1", type=float, default=1.0, help="first rod length")
    parser.add_argument("--l2", type=float, default=1.0, help="second rod length")
    parser.add_argument("--g", type=float, default=9.81, help="gravity")
    parser.add_argument("--duration", type=float, default=100.0, help="simulation time in seconds")
    parser.add_argument("--dt", type=float, default=0.01, help="time step in seconds")
    parser.add_argument("--fps", type=float, default=30.0, help="target average render fps")
    parser.add_argument("--min-fps", type=float, default=10.0, help="minimum adaptive render fps")
    parser.add_argument("--max-fps", type=float, default=120.0, help="maximum adaptive render fps")
    parser.add_argument(
        "--auto-close",
        action="store_true",
        help="close the window automatically when the animation ends",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    animate_pendulum(
        theta1_deg=args.theta1,
        theta2_deg=args.theta2,
        omega1=args.omega1,
        omega2=args.omega2,
        m1=args.m1,
        m2=args.m2,
        l1=args.l1,
        l2=args.l2,
        g=args.g,
        dt=args.dt,
        duration=args.duration,
        keep_open=not args.auto_close,
        target_fps=args.fps,
        min_fps=args.min_fps,
        max_fps=args.max_fps,
    )
