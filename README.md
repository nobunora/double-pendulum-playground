# Double Pendulum Playground

Interactive Python experiments for exploring double pendulum dynamics in 2D, 3D, Poincare sections, and FTLE-based chaos maps.

## Documentation

- English/Japanese guide: [docs/index.md](docs/index.md)
- Sample images: [docs/images](docs/images)

## Included Scripts

- `double_pendulum.py`
  - 2D double pendulum animation with a persistent trajectory.
  - Adaptive playback tuned to keep rendering responsive in Tkinter.
- `double_pendulum_3d.py`
  - 3D double pendulum viewer with mouse rotation and zoom.
  - Both moving masses leave visible trajectories in 3D projection.
- `double_pendulum_poincare.py`
  - Poincare section viewer for comparing more regular and more chaotic initial conditions.
  - GUI controls let you change masses, lengths, and initial angles, then recalculate.
- `double_pendulum_chaos_map.py`
  - Chaos heatmap over the `theta1-theta2` plane using a finite-time Lyapunov exponent.
  - Progressive rendering, stop/restart controls, multiprocessing, and vectorized FTLE batches.

## Requirements

- Python 3.11 or later
- `numpy`
- `tkinter`

Install NumPy with:

```powershell
python -m pip install numpy
```

## Quick Start

Run any script from this directory:

```powershell
python double_pendulum.py
python double_pendulum_3d.py
python double_pendulum_poincare.py
python double_pendulum_chaos_map.py
```

## Script Details

### 2D Animation

```powershell
python double_pendulum.py --theta1 120 --theta2 -10 --duration 100 --dt 0.01
```

Useful options:

- `--theta1`, `--theta2`
- `--omega1`, `--omega2`
- `--duration`
- `--dt`
- `--fps`, `--min-fps`, `--max-fps`
- `--auto-close`

Controls:

- `q` or `Esc`: close the window
- Resize the window to restart playback from `t = 0`

### 3D Animation

```powershell
python double_pendulum_3d.py --duration 20 --dt 0.005
```

Useful options:

- `--azimuth1`, `--elevation1`
- `--azimuth2`, `--elevation2`
- `--omega1x`, `--omega1y`, `--omega1z`
- `--omega2x`, `--omega2y`, `--omega2z`
- `--duration`
- `--dt`
- `--auto-close`

Controls:

- Drag with the left mouse button: rotate the camera
- Mouse wheel: zoom
- `q` or `Esc`: close the window

### Poincare Section Viewer

```powershell
python double_pendulum_poincare.py --duration 600 --dt 0.01
```

GUI inputs:

- `m1`, `m2`, `l1`, `l2`
- Regular-side `theta1`, `theta2`
- Chaotic-side `theta1`, `theta2`

Controls:

- `Recalculate`: run again with the current GUI values
- `q` or `Esc`: close the window

### Chaos Heatmap

```powershell
python double_pendulum_chaos_map.py --duration 40 --dt 0.02
```

GUI inputs:

- `m1`, `m2`, `l1`, `l2`
- `omega1`, `omega2`
- `grid`
- `duration`
- `dt`

Controls:

- `Compute Heatmap`: start a new FTLE map
- `Stop`: interrupt the current computation
- `q` or `Esc`: close the window

## Notes

- The chaos heatmap uses a finite-time Lyapunov exponent, so results depend on `duration`, `dt`, and the chosen perturbation model.
- The 3D viewer is a constrained free-direction pendulum visualization, not a rigid-body physics engine.
- All GUI tools use Tkinter, so they should run on a plain Python installation on Windows without extra GUI frameworks.

## License

This project is released under the MIT License. See `LICENSE` for details.
