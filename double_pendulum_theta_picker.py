import argparse
import subprocess
import sys
import tkinter as tk
from pathlib import Path


THETA_MIN = -180.0
THETA_MAX = 180.0


def show_picker(
    omega1=0.0,
    omega2=0.0,
    m1=1.0,
    m2=1.0,
    l1=1.0,
    l2=1.0,
    g=9.81,
    dt=0.02,
    duration=40.0,
):
    root = tk.Tk()
    root.title("Double Pendulum Theta Picker")
    root.geometry("920x760")
    root.minsize(760, 620)

    controls = tk.Frame(root, bg="#cbd5e1", padx=12, pady=10)
    controls.pack(fill="x")
    canvas = tk.Canvas(root, bg="#e2e8f0", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    vars_map = {
        "theta1": tk.StringVar(value="0.0"),
        "theta2": tk.StringVar(value="0.0"),
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
    status_var = tk.StringVar(value="Click anywhere in the theta plane to set theta1/theta2.")

    state = {
        "plot_bounds": None,
        "point": {"theta1": 0.0, "theta2": 0.0},
    }

    def make_labeled_entry(parent, label, variable, width=8):
        frame = tk.Frame(parent, bg="#cbd5e1")
        frame.pack(side="left", padx=(0, 10))
        tk.Label(frame, text=label, bg="#cbd5e1", fg="#0f172a", font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
        tk.Entry(frame, textvariable=variable, width=width, font=("Consolas", 11)).pack()

    make_labeled_entry(controls, "theta1", vars_map["theta1"], width=8)
    make_labeled_entry(controls, "theta2", vars_map["theta2"], width=8)
    make_labeled_entry(controls, "omega1", vars_map["omega1"], width=7)
    make_labeled_entry(controls, "omega2", vars_map["omega2"], width=7)
    make_labeled_entry(controls, "m1", vars_map["m1"], width=6)
    make_labeled_entry(controls, "m2", vars_map["m2"], width=6)
    make_labeled_entry(controls, "l1", vars_map["l1"], width=6)
    make_labeled_entry(controls, "l2", vars_map["l2"], width=6)
    make_labeled_entry(controls, "g", vars_map["g"], width=6)
    make_labeled_entry(controls, "dt", vars_map["dt"], width=6)
    make_labeled_entry(controls, "duration", vars_map["duration"], width=8)

    status_label = tk.Label(
        controls,
        textvariable=status_var,
        bg="#cbd5e1",
        fg="#334155",
        font=("Yu Gothic UI", 10),
        padx=10,
    )
    status_label.pack(side="right")

    def build_axis_ticks():
        return [(-180.0, "-180"), (-90.0, "-90"), (0.0, "0"), (90.0, "90"), (180.0, "180")]

    def theta_to_canvas(theta1, theta2):
        bounds = state["plot_bounds"]
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        x = left + (theta1 - THETA_MIN) / (THETA_MAX - THETA_MIN) * (right - left)
        y = top + (THETA_MAX - theta2) / (THETA_MAX - THETA_MIN) * (bottom - top)
        return x, y

    def canvas_to_theta(x, y):
        bounds = state["plot_bounds"]
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        if not (left <= x <= right and top <= y <= bottom):
            return None
        theta1 = THETA_MIN + (x - left) / (right - left) * (THETA_MAX - THETA_MIN)
        theta2 = THETA_MAX - (y - top) / (bottom - top) * (THETA_MAX - THETA_MIN)
        return theta1, theta2

    def redraw(_event=None):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)

        canvas.create_text(
            24,
            16,
            anchor="nw",
            text="Theta Picker for Double Pendulum",
            fill="#0f172a",
            font=("Yu Gothic UI", 18, "bold"),
        )
        canvas.create_text(
            24,
            46,
            anchor="nw",
            text="Click a point to set theta1/theta2, then launch the simulator.",
            fill="#334155",
            font=("Yu Gothic UI", 11),
        )

        left = 70
        top = 100
        plot_size = max(1, min(width - 150, height - 170))
        right = left + plot_size
        bottom = top + plot_size
        state["plot_bounds"] = (left, top, right, bottom)

        canvas.create_rectangle(left, top, right, bottom, fill="#f8fafc", outline="#cbd5e1")
        for angle_deg, label in build_axis_ticks():
            x = left + (angle_deg - THETA_MIN) / (THETA_MAX - THETA_MIN) * plot_size
            y = top + (THETA_MAX - angle_deg) / (THETA_MAX - THETA_MIN) * plot_size
            canvas.create_line(x, bottom, x, bottom + 6, fill="#475569")
            canvas.create_text(x, bottom + 22, text=label, fill="#475569", font=("Consolas", 10))
            canvas.create_line(left - 6, y, left, y, fill="#475569")
            canvas.create_text(left - 10, y, text=label, anchor="e", fill="#475569", font=("Consolas", 10))

        canvas.create_text((left + right) / 2.0, bottom + 42, text="theta1 (deg)", fill="#334155", font=("Yu Gothic UI", 10, "bold"))
        canvas.create_text(left - 42, (top + bottom) / 2.0, text="theta2 (deg)", angle=90, fill="#334155", font=("Yu Gothic UI", 10, "bold"))

        point = theta_to_canvas(state["point"]["theta1"], state["point"]["theta2"])
        if point is not None:
            x, y = point
            canvas.create_line(x, top, x, bottom, fill="#dc2626", dash=(6, 4), width=2)
            canvas.create_line(left, y, right, y, fill="#dc2626", dash=(6, 4), width=2)
            canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#dc2626", outline="white", width=1)

    def on_canvas_click(event):
        theta = canvas_to_theta(event.x, event.y)
        if theta is None:
            status_var.set("Click inside the theta plane.")
            return
        state["point"]["theta1"], state["point"]["theta2"] = theta
        vars_map["theta1"].set(f"{theta[0]:.3f}")
        vars_map["theta2"].set(f"{theta[1]:.3f}")
        status_var.set(f"Selected theta1={theta[0]:.3f}, theta2={theta[1]:.3f}")
        redraw()

    def parse_value(key):
        return float(vars_map[key].get())

    def launch_simulator():
        try:
            simulator_path = Path(__file__).resolve().parent / "double_pendulum.py"
            command = [
                sys.executable,
                str(simulator_path),
                "--theta1",
                f"{parse_value('theta1'):.10g}",
                "--theta2",
                f"{parse_value('theta2'):.10g}",
                "--omega1",
                f"{parse_value('omega1'):.10g}",
                "--omega2",
                f"{parse_value('omega2'):.10g}",
                "--m1",
                f"{parse_value('m1'):.10g}",
                "--m2",
                f"{parse_value('m2'):.10g}",
                "--l1",
                f"{parse_value('l1'):.10g}",
                "--l2",
                f"{parse_value('l2'):.10g}",
                "--g",
                f"{parse_value('g'):.10g}",
                "--dt",
                f"{parse_value('dt'):.10g}",
                "--duration",
                f"{parse_value('duration'):.10g}",
            ]
            subprocess.Popen(command, cwd=str(simulator_path.parent))
        except Exception as exc:
            status_var.set(f"Failed to launch simulator: {exc}")
            return

        status_var.set("Launched double_pendulum.py")

    launch_button = tk.Button(
        controls,
        text="Launch Simulator",
        command=launch_simulator,
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        font=("Yu Gothic UI", 10, "bold"),
        padx=14,
        pady=4,
    )
    launch_button.pack(side="left", padx=(8, 8))

    canvas.bind("<Button-1>", on_canvas_click)
    root.bind("<Configure>", redraw)
    root.bind("<KeyPress-q>", lambda _event: root.destroy())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.after(0, redraw)
    root.focus_force()
    root.mainloop()


def parse_args():
    parser = argparse.ArgumentParser(description="Pick theta1/theta2 by clicking and launch double_pendulum.py")
    parser.add_argument("--omega1", type=float, default=0.0)
    parser.add_argument("--omega2", type=float, default=0.0)
    parser.add_argument("--m1", type=float, default=1.0)
    parser.add_argument("--m2", type=float, default=1.0)
    parser.add_argument("--l1", type=float, default=1.0)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--g", type=float, default=9.81)
    parser.add_argument("--dt", type=float, default=0.02)
    parser.add_argument("--duration", type=float, default=40.0)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    show_picker(
        omega1=args.omega1,
        omega2=args.omega2,
        m1=args.m1,
        m2=args.m2,
        l1=args.l1,
        l2=args.l2,
        g=args.g,
        dt=args.dt,
        duration=args.duration,
    )
