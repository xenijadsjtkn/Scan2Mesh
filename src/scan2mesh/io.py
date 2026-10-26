"""Point-cloud import, including stored E57 scan poses."""

from pathlib import Path

import numpy as np
import open3d as o3d
import pye57
from plyfile import PlyData, PlyParseError

SUPPORTED_FORMATS = {".ply", ".pcd", ".xyz", ".xyzn", ".xyzrgb", ".pts", ".e57"}


def load_cloud(path: Path) -> tuple[o3d.geometry.PointCloud, dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Point cloud does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported input format: {path.suffix}. Export RCP/RCS to E57 or PLY first.")
    if path.suffix.lower() == ".ply":
        # Open3D's legacy PLY reader may return a partially populated cloud on
        # parse failure. Use a parser that rejects truncated/malformed inputs.
        try:
            vertices = PlyData.read(str(path))["vertex"]
            points = np.column_stack([vertices[axis] for axis in "xyz"]).astype(float)
            cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
            fields = vertices.data.dtype.names
            if all(channel in fields for channel in ("red", "green", "blue")):
                channels = [vertices[channel] for channel in ("red", "green", "blue")]
                limits = [np.iinfo(channel.dtype).max if np.issubdtype(channel.dtype, np.integer) else 1 for channel in channels]
                colors = np.column_stack(channels).astype(float) / limits
                cloud.colors = o3d.utility.Vector3dVector(np.clip(np.nan_to_num(colors), 0, 1))
        except (PlyParseError, ValueError, KeyError, TypeError, IndexError) as exc:
            raise ValueError(f"Invalid or truncated PLY point cloud: {path.name}: {exc}") from exc
        return cloud, {"format": "ply", "stored_poses_applied": False}
    if path.suffix.lower() != ".e57":
        cloud = o3d.io.read_point_cloud(
            str(path), remove_nan_points=False, remove_infinite_points=False
        )
        return cloud, {"format": path.suffix.lower()[1:], "stored_poses_applied": False}

    e57 = pye57.E57(str(path))
    chunks, color_chunks = [], []
    source_points = 0
    scan_count = e57.scan_count
    try:
        for index in range(scan_count):
            source_points += e57.get_header(index).point_count
            data = e57.read_scan(index, colors=True, transform=True, ignore_missing_fields=True)
            points = np.column_stack([data[f"cartesian{axis}"] for axis in "XYZ"])
            chunks.append(points)
            if all(f"color{channel}" in data for channel in ("Red", "Green", "Blue")):
                colors = np.column_stack([data[f"color{channel}"] for channel in ("Red", "Green", "Blue")])
                color_chunks.append(np.clip(colors.astype(float) / 255, 0, 1))
            else:
                color_chunks.append(np.full(points.shape, 0.65))
    finally:
        e57.image_file.close()
    cloud = o3d.geometry.PointCloud()
    if chunks:
        cloud.points = o3d.utility.Vector3dVector(np.concatenate(chunks))
        cloud.colors = o3d.utility.Vector3dVector(np.concatenate(color_chunks))
    return cloud, {
        "format": "e57", "scan_count": scan_count,
        "stored_poses_applied": True, "source_points_including_invalid": int(source_points),
        "note": "Stored poses applied; scans are not re-registered. Invalid-state E57 points are excluded by the importer.",
    }
