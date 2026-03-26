import argparse
import math
import tkinter as tk

import numpy as np


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
    steps = int(duration / dt)
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


def animate_pendulum(
    x1,
    y1,
    x2,
    y2,
    dt,
    keep_open=True,
    target_fps=30.0,
    min_fps=10.0,
    max_fps=120.0,
):
    root = tk.Tk()
    root.title("Double Pendulum")
    root.geometry("900x760")
    root.minsize(700, 600)
    root.resizable(True, True)

    canvas = tk.Canvas(root, bg="white", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    total_frames = len(x1)
    trace_chunk_points = 64
    playback_frames, playback_delays_ms = build_playback_schedule(
        x2=x2,
        y2=y2,
        dt=dt,
        target_fps=target_fps,
        min_fps=min_fps,
        max_fps=max_fps,
    )

    state = {
        "frame": playback_frames[0],
        "playback_index": 0,
        "job": None,
        "running": True,
        "finished": False,
        "trace_frame": 0,
        "resize_job": None,
        "viewport_width": 900,
        "viewport_height": 760,
    }
    reach = float(np.max(np.abs(np.concatenate([x1, y1, x2, y2])))) + 0.25
    items = {}
    trace_state = {
        "items": [],
        "last_screen": None,
        "current_item": None,
        "current_coords": [],
    }

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
            (state["viewport_width"] - 2 * margin) / (2 * reach),
            (state["viewport_height"] - 2 * margin) / (2 * reach),
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
            trace_state["last_screen"] = world_to_screen(float(x2[0]), float(y2[0]))

        if frame <= state["trace_frame"]:
            return

        for index in range(state["trace_frame"] + 1, frame + 1):
            sx, sy = world_to_screen(float(x2[index]), float(y2[index]))
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
        p1x, p1y = world_to_screen(float(x1[frame]), float(y1[frame]))
        p2x, p2y = world_to_screen(float(x2[frame]), float(y2[frame]))

        canvas.itemconfigure(items["time"], text=f"t = {frame * dt:5.2f} s")
        canvas.coords(items["x_axis"], 0, state["viewport_height"] / 2, state["viewport_width"], state["viewport_height"] / 2)
        canvas.coords(items["y_axis"], state["viewport_width"] / 2, 0, state["viewport_width"] / 2, state["viewport_height"])
        canvas.coords(items["rod"], ox, oy, p1x, p1y, p2x, p2y)
        set_circle(items["origin"], ox, oy, 5)
        set_circle(items["bob1"], p1x, p1y, 10)
        set_circle(items["bob2"], p2x, p2y, 10)

    def schedule_next_step():
        if len(playback_frames) > 1 and state["running"] and not state["finished"]:
            delay_ms = playback_delays_ms[state["playback_index"]]
            state["job"] = root.after(delay_ms, step)

    def restart_animation():
        state["resize_job"] = None
        if not state["running"]:
            return

        if state["job"] is not None:
            root.after_cancel(state["job"])
            state["job"] = None

        state["frame"] = playback_frames[0]
        state["playback_index"] = 0
        state["finished"] = False
        state["trace_frame"] = 0
        clear_trace()
        trace_state["last_screen"] = world_to_screen(float(x2[0]), float(y2[0]))
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
        frame = playback_frames[playback_index]

        if frame != state["frame"]:
            state["frame"] = frame
        append_trace_until(frame)
        update_scene()

        if playback_index >= len(playback_frames) - 1 or frame >= total_frames - 1:
            state["finished"] = True
            state["frame"] = total_frames - 1
            append_trace_until(total_frames - 1)
            update_scene()
            if not keep_open:
                state["job"] = root.after(300, close_window)
            return

        state["playback_index"] += 1
        schedule_next_step()

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
    trace_state["last_screen"] = world_to_screen(float(x2[0]), float(y2[0]))
    canvas.bind("<Configure>", on_resize)
    update_scene()
    schedule_next_step()
    root.focus_force()
    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Animate a double pendulum.")
    parser.add_argument("--theta1", type=float, default=120.0, help="first angle in degrees")
    parser.add_argument("--theta2", type=float, default=-10.0, help="second angle in degrees")
    parser.add_argument("--omega1", type=float, default=0.0, help="first angular velocity")
    parser.add_argument("--omega2", type=float, default=0.0, help="second angular velocity")
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
    x1, y1, x2, y2 = simulate(
        theta1_deg=args.theta1,
        theta2_deg=args.theta2,
        omega1=args.omega1,
        omega2=args.omega2,
        dt=args.dt,
        duration=args.duration,
    )
    animate_pendulum(
        x1,
        y1,
        x2,
        y2,
        args.dt,
        keep_open=not args.auto_close,
        target_fps=args.fps,
        min_fps=args.min_fps,
        max_fps=args.max_fps,
    )
