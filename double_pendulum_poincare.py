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


def simulate_states(
    theta1_deg,
    theta2_deg,
    omega1,
    omega2,
    m1=1.1,
    m2=1.0,
    l1=1.0,
    l2=1.1,
    g=9.81,
    dt=0.01,
    duration=4000.0,
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
    return states


def wrap_angle(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def extract_poincare_points(states, section_angle=0.0):
    points = []

    for index in range(len(states) - 1):
        theta2_a = states[index, 2] - section_angle
        theta2_b = states[index + 1, 2] - section_angle

        if theta2_a > 0.0 or theta2_b < 0.0:
            continue

        delta = theta2_b - theta2_a
        alpha = 0.0 if abs(delta) < 1e-12 else -theta2_a / delta

        omega2_cross = states[index, 3] + alpha * (states[index + 1, 3] - states[index, 3])
        if omega2_cross <= 0.0:
            continue

        theta1_cross = states[index, 0] + alpha * (states[index + 1, 0] - states[index, 0])
        omega1_cross = states[index, 1] + alpha * (states[index + 1, 1] - states[index, 1])
        points.append((wrap_angle(theta1_cross), omega1_cross))

    return np.asarray(points, dtype=float)


def compute_poincare_datasets(duration, dt, m1, m2, l1, l2, regular_theta1, regular_theta2, chaotic_theta1, chaotic_theta2):
    regular_states = simulate_states(
        theta1_deg=regular_theta1,
        theta2_deg=regular_theta2,
        omega1=0.0,
        omega2=0.0,
        m1=m1,
        m2=m2,
        l1=l1,
        l2=l2,
        dt=dt,
        duration=duration,
    )
    chaotic_states = simulate_states(
        theta1_deg=chaotic_theta1,
        theta2_deg=chaotic_theta2,
        omega1=0.0,
        omega2=0.0,
        m1=m1,
        m2=m2,
        l1=l1,
        l2=l2,
        dt=dt,
        duration=duration,
    )
    return extract_poincare_points(regular_states), extract_poincare_points(chaotic_states)


def draw_panel(canvas, rect, title, subtitle, points, y_limit, point_color):
    x0, y0, x1, y1 = rect
    width = x1 - x0
    height = y1 - y0
    margin_left = 54
    margin_right = 24
    margin_top = 68
    margin_bottom = 48

    plot_x0 = x0 + margin_left
    plot_y0 = y0 + margin_top
    plot_x1 = x1 - margin_right
    plot_y1 = y1 - margin_bottom

    canvas.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#cbd5e1", width=1)
    canvas.create_text(
        x0 + 18,
        y0 + 18,
        text=title,
        anchor="nw",
        fill="#0f172a",
        font=("Yu Gothic UI", 15, "bold"),
    )
    canvas.create_text(
        x0 + 18,
        y0 + 44,
        text=subtitle,
        anchor="nw",
        fill="#475569",
        font=("Yu Gothic UI", 10),
    )

    canvas.create_rectangle(plot_x0, plot_y0, plot_x1, plot_y1, fill="#f8fafc", outline="#cbd5e1")

    zero_x = plot_x0 + (-(-math.pi)) / (2.0 * math.pi) * (plot_x1 - plot_x0)
    zero_y = plot_y0 + (y_limit - 0.0) / (2.0 * y_limit) * (plot_y1 - plot_y0)
    canvas.create_line(plot_x0, zero_y, plot_x1, zero_y, fill="#cbd5e1")
    canvas.create_line(zero_x, plot_y0, zero_x, plot_y1, fill="#cbd5e1")

    tick_angles = [-math.pi, -math.pi / 2.0, 0.0, math.pi / 2.0, math.pi]
    tick_labels = ["-pi", "-pi/2", "0", "pi/2", "pi"]
    for angle, label in zip(tick_angles, tick_labels):
        x = plot_x0 + (angle + math.pi) / (2.0 * math.pi) * (plot_x1 - plot_x0)
        canvas.create_line(x, plot_y1, x, plot_y1 + 6, fill="#475569")
        canvas.create_text(x, plot_y1 + 20, text=label, fill="#475569", font=("Consolas", 10))

    for omega in (-y_limit, 0.0, y_limit):
        y = plot_y0 + (y_limit - omega) / (2.0 * y_limit) * (plot_y1 - plot_y0)
        canvas.create_line(plot_x0 - 6, y, plot_x0, y, fill="#475569")
        canvas.create_text(plot_x0 - 10, y, text=f"{omega:.1f}", anchor="e", fill="#475569", font=("Consolas", 10))

    canvas.create_text((plot_x0 + plot_x1) / 2.0, plot_y1 + 34, text="theta1", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
    canvas.create_text(plot_x0 - 36, (plot_y0 + plot_y1) / 2.0, text="omega1", angle=90, fill="#334155", font=("Yu Gothic UI", 10, "bold"))

    if len(points) == 0:
        canvas.create_text(
            (plot_x0 + plot_x1) / 2.0,
            (plot_y0 + plot_y1) / 2.0,
            text="No section points",
            fill="#94a3b8",
            font=("Yu Gothic UI", 12),
        )
        return

    for theta1, omega1 in points:
        px = plot_x0 + (theta1 + math.pi) / (2.0 * math.pi) * (plot_x1 - plot_x0)
        py = plot_y0 + (y_limit - omega1) / (2.0 * y_limit) * (plot_y1 - plot_y0)
        if plot_x0 <= px <= plot_x1 and plot_y0 <= py <= plot_y1:
            canvas.create_oval(px - 1.6, py - 1.6, px + 1.6, py + 1.6, fill=point_color, outline="")


def show_poincare_window(duration, dt, auto_close_ms=0):
    root = tk.Tk()
    root.title("Double Pendulum Poincare Section")
    root.geometry("1280x760")
    root.minsize(980, 620)

    controls = tk.Frame(root, bg="#cbd5e1", padx=12, pady=10)
    controls.pack(fill="x")
    canvas = tk.Canvas(root, bg="#e2e8f0", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    vars_map = {
        "m1": tk.StringVar(value="1.1"),
        "m2": tk.StringVar(value="1.0"),
        "l1": tk.StringVar(value="1.0"),
        "l2": tk.StringVar(value="1.0"),
        "regular_theta1": tk.StringVar(value="25.0"),
        "regular_theta2": tk.StringVar(value="5.0"),
        "chaotic_theta1": tk.StringVar(value="120.0"),
        "chaotic_theta2": tk.StringVar(value="-10.0"),
    }
    plot_state = {
        "regular_points": np.empty((0, 2), dtype=float),
        "chaotic_points": np.empty((0, 2), dtype=float),
        "params_text": "m1=1.1, m2=1.0, l1=1.0, l2=1.0",
        "regular_subtitle": "Example: theta1=25 deg, theta2=5 deg, omega1=0, omega2=0",
        "chaotic_subtitle": "Example: theta1=120 deg, theta2=-10 deg, omega1=0, omega2=0",
    }

    def make_labeled_entry(parent, label, variable):
        frame = tk.Frame(parent, bg="#cbd5e1")
        frame.pack(side="left", padx=(0, 10))
        tk.Label(frame, text=label, bg="#cbd5e1", fg="#0f172a", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
        tk.Entry(frame, textvariable=variable, width=8, font=("Consolas", 11)).pack()

    make_labeled_entry(controls, "m1", vars_map["m1"])
    make_labeled_entry(controls, "m2", vars_map["m2"])
    make_labeled_entry(controls, "l1", vars_map["l1"])
    make_labeled_entry(controls, "l2", vars_map["l2"])
    make_labeled_entry(controls, "reg th1", vars_map["regular_theta1"])
    make_labeled_entry(controls, "reg th2", vars_map["regular_theta2"])
    make_labeled_entry(controls, "chaos th1", vars_map["chaotic_theta1"])
    make_labeled_entry(controls, "chaos th2", vars_map["chaotic_theta2"])

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

    def redraw(_event=None):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        canvas.create_text(
            26,
            18,
            anchor="nw",
            text="Poincare Section: theta2 = 0 upward crossing",
            fill="#0f172a",
            font=("Yu Gothic UI", 18, "bold"),
        )
        canvas.create_text(
            26,
            48,
            anchor="nw",
            text=f"Closed curves suggest regular motion, while scattered clouds suggest chaotic motion.  {plot_state['params_text']}",
            fill="#334155",
            font=("Yu Gothic UI", 11),
        )

        top = 90
        gap = 18
        panel_width = (width - 3 * gap) / 2.0
        panel_height = height - top - 24

        combined = []
        if len(plot_state["regular_points"]):
            combined.append(np.abs(plot_state["regular_points"][:, 1]))
        if len(plot_state["chaotic_points"]):
            combined.append(np.abs(plot_state["chaotic_points"][:, 1]))
        omega_limit = 1.0 if not combined else max(1.0, float(np.max(np.concatenate(combined))) * 1.1)

        draw_panel(
            canvas=canvas,
            rect=(gap, top, gap + panel_width, top + panel_height),
            title="Regular-like Orbit",
            subtitle=plot_state["regular_subtitle"],
            points=plot_state["regular_points"],
            y_limit=omega_limit,
            point_color="#2563eb",
        )
        draw_panel(
            canvas=canvas,
            rect=(2 * gap + panel_width, top, 2 * gap + 2 * panel_width, top + panel_height),
            title="Chaotic Orbit",
            subtitle=plot_state["chaotic_subtitle"],
            points=plot_state["chaotic_points"],
            y_limit=omega_limit,
            point_color="#dc2626",
        )

    def parse_positive_float(name):
        value = float(vars_map[name].get())
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")
        return value

    def parse_float(name):
        return float(vars_map[name].get())

    def recompute():
        try:
            m1 = parse_positive_float("m1")
            m2 = parse_positive_float("m2")
            l1 = parse_positive_float("l1")
            l2 = parse_positive_float("l2")
            regular_theta1 = parse_float("regular_theta1")
            regular_theta2 = parse_float("regular_theta2")
            chaotic_theta1 = parse_float("chaotic_theta1")
            chaotic_theta2 = parse_float("chaotic_theta2")
        except ValueError as exc:
            status_var.set(str(exc))
            return

        status_var.set("Calculating...")
        recalc_button.config(state="disabled")
        root.update_idletasks()

        regular_points, chaotic_points = compute_poincare_datasets(
            duration=duration,
            dt=dt,
            m1=m1,
            m2=m2,
            l1=l1,
            l2=l2,
            regular_theta1=regular_theta1,
            regular_theta2=regular_theta2,
            chaotic_theta1=chaotic_theta1,
            chaotic_theta2=chaotic_theta2,
        )
        plot_state["regular_points"] = regular_points
        plot_state["chaotic_points"] = chaotic_points
        plot_state["params_text"] = f"m1={m1:.3g}, m2={m2:.3g}, l1={l1:.3g}, l2={l2:.3g}"
        plot_state["regular_subtitle"] = (
            f"theta1={regular_theta1:.3g} deg, theta2={regular_theta2:.3g} deg, omega1=0, omega2=0"
        )
        plot_state["chaotic_subtitle"] = (
            f"theta1={chaotic_theta1:.3g} deg, theta2={chaotic_theta2:.3g} deg, omega1=0, omega2=0"
        )
        status_var.set(f"Updated: regular={len(regular_points)} pts, chaotic={len(chaotic_points)} pts")
        recalc_button.config(state="normal")
        redraw()

    recalc_button = tk.Button(
        controls,
        text="Recalculate",
        command=recompute,
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        padx=14,
        pady=4,
    )
    recalc_button.pack(side="left", padx=(4, 8))

    root.bind("<Configure>", redraw)
    root.bind("<KeyPress-q>", lambda _event: root.destroy())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.after(0, recompute)
    root.focus_force()

    if auto_close_ms > 0:
        root.after(auto_close_ms, root.destroy)

    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Show Poincare sections of a double pendulum.")
    parser.add_argument("--duration", type=float, default=600.0, help="simulation time in seconds")
    parser.add_argument("--dt", type=float, default=0.01, help="time step in seconds")
    parser.add_argument("--auto-close-ms", type=int, default=0, help="auto close the window after N milliseconds")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    show_poincare_window(
        duration=args.duration,
        dt=args.dt,
        auto_close_ms=args.auto_close_ms,
    )
