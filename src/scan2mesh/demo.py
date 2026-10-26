"""Synthetic industrial bay with a doorway, pipes, noise and outliers."""

from pathlib import Path

import numpy as np
import open3d as o3d


def generate_demo(output: Path, seed: int = 7) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Demo output already exists: {output}")
    if output.suffix.lower() != ".ply":
        raise ValueError("Demo output must have the .ply extension")
    rng = np.random.default_rng(seed)
    pieces, colors = [], []

    def add(points, color):
        pieces.append(points)
        colors.append(np.tile(color, (len(points), 1)))

    x, y = np.meshgrid(np.arange(0, 6.01, 0.07), np.arange(0, 4.01, 0.07))
    add(np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)]), [0.6, 0.6, 0.6])
    x, z = np.meshgrid(np.arange(0, 6.01, 0.07), np.arange(0, 3.01, 0.07))
    wall = np.column_stack([x.ravel(), np.full(x.size, 4), z.ravel()])
    doorway = (wall[:, 0] > 2) & (wall[:, 0] < 3.2) & (wall[:, 2] < 2.1)
    add(wall[~doorway], [0.7, 0.75, 0.8])
    y, z = np.meshgrid(np.arange(0, 4.01, 0.07), np.arange(0, 3.01, 0.07))
    add(np.column_stack([np.zeros(y.size), y.ravel(), z.ravel()]), [0.7, 0.75, 0.8])
    along, theta = np.meshgrid(np.linspace(0.5, 5.5, 120), np.linspace(0, 2 * np.pi, 48, endpoint=False))
    add(np.column_stack([along.ravel(), 2.5 + 0.12 * np.cos(theta.ravel()), 2.2 + 0.12 * np.sin(theta.ravel())]), [0.9, 0.55, 0.1])
    height, theta = np.meshgrid(np.linspace(0.2, 2.8, 80), np.linspace(0, 2 * np.pi, 36, endpoint=False))
    add(np.column_stack([4.8 + 0.1 * np.cos(theta.ravel()), 2 + 0.1 * np.sin(theta.ravel()), height.ravel()]), [0.9, 0.55, 0.1])
    points = np.concatenate(pieces)
    points += rng.normal(0, 0.003, points.shape)
    points = np.concatenate([points, points[:50], rng.uniform([-1, -1, -0.8], [7, 5, 4], size=(150, 3))])
    color_array = np.concatenate(colors)
    color_array = np.concatenate([color_array, color_array[:50], np.full((150, 3), 0.9)])
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.colors = o3d.utility.Vector3dVector(color_array)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(output), cloud):
        raise OSError(f"Could not write demo: {output}")
    return {"output": str(output), "points": len(points), "units": "metres", "synthetic": True}
