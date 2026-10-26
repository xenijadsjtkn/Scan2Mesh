"""Measured reconstruction of already registered point-cloud excerpts.

All lengths are expressed in the input coordinate units. No semantic labels or
intentional hole filling are inferred here.
"""

import copy
import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import open3d as o3d

from . import __version__
from .io import load_cloud


@dataclass(frozen=True)
class PipelineConfig:
    voxel_size: float = 0.0
    outlier_neighbors: int = 20
    outlier_std_ratio: float = 2.0
    plane_distance: float = 0.01
    max_planes: int = 3
    min_plane_points: int = 100
    reconstruction: str = "ball-pivoting"
    normal_radius: float | None = None
    ball_radius: float | None = None
    poisson_depth: int = 8
    seed: int = 7
    crop: tuple[float, float, float, float, float, float] | None = None

    def __post_init__(self):
        if not math.isfinite(self.voxel_size) or self.voxel_size < 0:
            raise ValueError("voxel_size must be finite and >= 0")
        for name in ("outlier_std_ratio", "plane_distance", "normal_radius", "ball_radius"):
            value = getattr(self, name)
            if value is None and name in ("normal_radius", "ball_radius"):
                continue
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0")
        for name, lower in (("outlier_neighbors", 2), ("max_planes", 0), ("min_plane_points", 3), ("seed", 0)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")
        if not isinstance(self.poisson_depth, int) or not 4 <= self.poisson_depth <= 10:
            raise ValueError("poisson_depth must be an integer between 4 and 10 (memory bounded prototype)")
        if self.seed >= 2**31:
            raise ValueError("seed must be < 2**31")
        if self.reconstruction not in ("ball-pivoting", "poisson"):
            raise ValueError("reconstruction must be ball-pivoting or poisson")
        if self.crop is not None:
            if len(self.crop) != 6 or not np.isfinite(self.crop).all():
                raise ValueError("crop must contain six finite coordinates")
            if np.any(np.asarray(self.crop[:3]) >= np.asarray(self.crop[3:])):
                raise ValueError("crop minima must be smaller than maxima")


def _summarize(distances: np.ndarray) -> dict:
    if len(distances) == 0 or not np.isfinite(distances).all():
        raise ValueError("Distance evaluation did not produce finite measurements")
    return {
        "median": float(np.median(distances)),
        "p95": float(np.quantile(distances, 0.95)),
        "max": float(np.max(distances)),
    }


def _sample_rows(points: np.ndarray, limit: int, rng) -> np.ndarray:
    if len(points) <= limit:
        return points
    return points[rng.choice(len(points), limit, replace=False)]


def _segment_planes(cloud, config, origin):
    segmented = copy.deepcopy(cloud)
    segmented.paint_uniform_color([0.55, 0.55, 0.55])
    colors = np.asarray(segmented.colors)
    remaining = np.arange(len(cloud.points))
    palette = np.array([[0.9, 0.3, 0.2], [0.2, 0.65, 0.9], [0.25, 0.8, 0.4], [0.9, 0.7, 0.2]])
    planes = []
    for index in range(config.max_planes):
        if len(remaining) < config.min_plane_points:
            break
        subset = cloud.select_by_index(remaining.tolist())
        model, inliers = subset.segment_plane(
            distance_threshold=config.plane_distance, ransac_n=3,
            num_iterations=1_000, probability=0.999,
        )
        if len(inliers) < config.min_plane_points:
            break
        model = np.asarray(model, dtype=float)
        model /= np.linalg.norm(model[:3])
        if model[np.argmax(np.abs(model[:3]))] < 0:
            model *= -1
        indices = remaining[np.asarray(inliers)]
        residual = np.asarray(cloud.points)[indices] @ model[:3] + model[3]
        planes.append({
            "id": index, "normal": model[:3].tolist(),
            "offset": float(model[3] - model[:3] @ origin),
            "point_count": int(len(indices)),
            "rms_distance": float(np.sqrt(np.mean(residual**2))),
        })
        colors[indices] = palette[index % len(palette)]
        keep = np.ones(len(remaining), dtype=bool)
        keep[inliers] = False
        remaining = remaining[keep]
    return segmented, planes


def _prepare_normals(cloud, radius):
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=50))
    points = np.asarray(cloud.points)
    covariance = np.cov(points.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    if eigenvalues[1] <= np.finfo(float).eps * max(eigenvalues[-1], 1):
        raise ValueError("Point cloud is effectively a line; surface reconstruction needs 2D or 3D support")
    if eigenvalues[0] <= eigenvalues[-1] * 1e-8:
        # Tangent-plane propagation uses a 3D Delaunay graph, undefined for an
        # exactly planar cloud. Orient its normals using the fitted plane instead.
        direction = eigenvectors[:, 0]
        normals = np.asarray(cloud.normals)
        normals[normals @ direction < 0] *= -1
    else:
        cloud.orient_normals_consistent_tangent_plane(min(30, len(points) - 1))
    cloud.normalize_normals()


def _reconstruct(cloud, config, nearest_distances):
    density_summary = None
    radii = []
    if config.reconstruction == "ball-pivoting":
        if config.ball_radius is not None:
            radii = [config.ball_radius, 2 * config.ball_radius]
        else:
            # A median-only radius can exceed the radius of densely scanned
            # pipes while the same cloud contains much sparser hall surfaces.
            # Start small and progressively cover the observed density range.
            low, high = np.quantile(nearest_distances[nearest_distances > 0], [0.1, 0.9])
            # Points from adjacent voxels can still be arbitrarily close. The
            # requested voxel scale gives a useful lower sampling bound; an
            # excessively small first pass can strand disconnected surfaces in
            # Open3D's later border-expansion passes.
            radii = [float(1.5 * max(low, config.voxel_size))]
            maximum = float(max(radii[0], 2 * high))
            while radii[-1] < maximum and len(radii) < 8:
                radii.append(min(2 * radii[-1], maximum))
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            cloud, o3d.utility.DoubleVector(radii)
        )
    else:
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            cloud, depth=config.poisson_depth, n_threads=4
        )
        density_summary = _summarize(np.asarray(densities))
        # Do not hide invented geometry by implicitly cropping or trimming it.
        # The distance report exposes it for comparison with the open method.
    mesh.remove_duplicated_vertices()
    mesh.remove_duplicated_triangles()
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    if len(mesh.triangles) == 0:
        raise ValueError("Reconstruction produced no triangles; check point spacing and normal/ball radius")
    mesh.compute_vertex_normals()
    return mesh, radii, density_summary


def _quality(mesh, cleaned, original, seed):
    rng = np.random.default_rng(seed)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))

    def to_mesh(points):
        return scene.compute_distance(o3d.core.Tensor(np.asarray(points, dtype=np.float32))).numpy()

    cleaned_samples = _sample_rows(np.asarray(cleaned.points), 50_000, rng)
    original_samples = _sample_rows(np.asarray(original.points), 50_000, rng)
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    centroids = vertices[triangles].mean(axis=1)
    area_samples = np.asarray(mesh.sample_points_uniformly(number_of_points=20_000).points)
    mesh_samples = np.concatenate([
        _sample_rows(vertices, 10_000, rng), _sample_rows(centroids, 10_000, rng), area_samples
    ])
    mesh_sample_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(mesh_samples))
    to_cloud = np.asarray(mesh_sample_cloud.compute_point_cloud_distance(cleaned))
    edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    _, component_counts, _ = mesh.cluster_connected_triangles()
    return {
        "point_to_mesh": _summarize(to_mesh(cleaned_samples)),
        "mesh_to_cloud": _summarize(to_cloud),
        "original_to_mesh": _summarize(to_mesh(original_samples)),
        "sample_counts": {
            "cleaned_points": len(cleaned_samples), "original_points": len(original_samples),
            "mesh_surface": len(mesh_samples),
        },
        "boundary_edges": int(np.count_nonzero(edge_counts == 1)),
        "non_manifold_edges": int(np.count_nonzero(edge_counts > 2)),
        "connected_components": len(component_counts), "watertight": bool(mesh.is_watertight()),
        "note": "Distances use input units. Original reference includes finite cropped points before cleaning. Mesh-to-cloud is sampled and uses the cleaned cloud; maxima are sample maxima, not Hausdorff bounds.",
    }


def run_pipeline(input_path: Path, output_dir: Path, config: PipelineConfig) -> dict:
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).absolute()
    if output_dir.is_symlink() or (output_dir.exists() and (
        not output_dir.is_dir() or any(output_dir.iterdir())
    )):
        raise FileExistsError(f"Output must be a new or empty directory: {output_dir}")
    o3d.utility.random.seed(config.seed)
    cloud, import_info = load_cloud(input_path)
    counts = {"input_points": len(cloud.points)}
    finite_indices = np.flatnonzero(np.isfinite(np.asarray(cloud.points)).all(axis=1))
    cloud = cloud.select_by_index(finite_indices.tolist())
    counts["finite_points"] = len(cloud.points)
    if config.crop is not None:
        cloud = cloud.crop(o3d.geometry.AxisAlignedBoundingBox(config.crop[:3], config.crop[3:]))
    counts["cropped_points"] = len(cloud.points)
    if len(cloud.points) < 30:
        raise ValueError("At least 30 finite points inside the selected region are required")

    # Work locally even for georeferenced sites. Ray casting uses float32 and
    # would otherwise lose small details at coordinates in the millions.
    # A bbox midpoint is pulled far away by a single extreme outlier, defeating
    # the precision benefit before that outlier can be removed.
    origin = np.median(np.asarray(cloud.points), axis=0)
    cloud.translate(-origin)
    original = copy.deepcopy(cloud)
    cloud.remove_duplicated_points()
    counts["deduplicated_points"] = len(cloud.points)
    if config.voxel_size > 0:
        cloud = cloud.voxel_down_sample(config.voxel_size)
    counts["downsampled_points"] = len(cloud.points)
    if len(cloud.points) < 30:
        raise ValueError("Too few points remain after downsampling; reduce voxel_size")
    cloud, _ = cloud.remove_statistical_outlier(
        nb_neighbors=min(config.outlier_neighbors, len(cloud.points) - 1),
        std_ratio=config.outlier_std_ratio,
    )
    counts["cleaned_points"] = len(cloud.points)
    counts["removed_outliers"] = counts["downsampled_points"] - counts["cleaned_points"]
    if len(cloud.points) < 30:
        raise ValueError("Too few points remain after outlier removal")
    nearest = np.asarray(cloud.compute_nearest_neighbor_distance())
    spacing = float(np.median(nearest[nearest > 0]))
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("Could not determine positive point spacing")
    normal_radius = config.normal_radius or max(4 * spacing, 2 * config.voxel_size)
    _prepare_normals(cloud, normal_radius)
    segmented, planes = _segment_planes(cloud, config, origin)
    mesh, ball_radii, density_summary = _reconstruct(cloud, config, nearest)
    quality = _quality(mesh, cloud, original, config.seed)
    counts.update(mesh_vertices=len(mesh.vertices), mesh_triangles=len(mesh.triangles))
    report = {
        "schema_version": 1, "scan2mesh_version": __version__,
        "open3d_version": o3d.__version__, "input_path": str(input_path),
        "config": json.loads(json.dumps(asdict(config))), "import": import_info,
        "counts": counts, "planes": planes, "quality": quality,
        "analysis": {
            "coordinate_origin": origin.tolist(), "median_nearest_neighbor_distance": spacing,
            "normal_radius": normal_radius, "ball_radii": ball_radii
            if config.reconstruction == "ball-pivoting" else None,
            "poisson_vertex_density": density_summary,
        },
        "limitations": [
            "Geometric plane detection only; no semantic object labels or cylinder fitting.",
            "No explicit hole filling or protected openings. Either reconstruction method may bridge gaps.",
            "Already registered excerpts only; input is loaded in memory. No accuracy acceptance threshold is implied.",
        ],
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Publish results together. Failed processing never leaves plausible partial
    # results under the requested output name, nor overwrites a previous run.
    with tempfile.TemporaryDirectory(prefix=".scan2mesh-", dir=output_dir.parent) as temporary:
        staged = Path(temporary) / "result"
        staged.mkdir()
        for filename, output_cloud in (("cleaned.ply", cloud), ("segments.ply", segmented)):
            output_cloud.translate(origin)
            if not o3d.io.write_point_cloud(str(staged / filename), output_cloud):
                raise OSError(f"Could not write {filename}")
        mesh.translate(origin)
        if not o3d.io.write_triangle_mesh(str(staged / "mesh.ply"), mesh):
            raise OSError("Could not write mesh.ply")
        (staged / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        if output_dir.exists():
            output_dir.rmdir()  # Only an empty directory may be replaced.
        staged.rename(output_dir)
    return report
