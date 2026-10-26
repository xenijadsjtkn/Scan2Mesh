"""Conservative geometric planar patches for experimental local reconstruction.

These are surface patches, not semantic objects. Triangulation preserves gaps
larger than its local support scale; openings at or below the sampling spacing
cannot be guaranteed. Rejected patches remain unclassified. Unused boundary
points of accepted patches are reported without retriangulating their gaps.
"""

from dataclasses import dataclass

import numpy as np
import open3d as o3d
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import Delaunay, QhullError, cKDTree


@dataclass(frozen=True)
class PlanarPatch:
    indices: np.ndarray
    normal: np.ndarray
    offset: float
    rms_distance: float
    spacing: float


def _local_scales(points: np.ndarray) -> np.ndarray:
    """Estimate 2D sampling scale from six neighbours, not a single near twin."""
    k = min(6, len(points) - 1)
    if k < 1:
        return np.zeros(len(points))
    distances, _ = cKDTree(points).query(points, k=k + 1, workers=1)
    return distances[:, -1] * np.sqrt(np.pi / k)


def _connected_support(points: np.ndarray) -> list[np.ndarray]:
    if len(points) < 3:
        return []
    scales = _local_scales(points)
    distances, neighbours = cKDTree(points).query(points, k=min(13, len(points)), workers=1)
    rows = np.broadcast_to(np.arange(len(points))[:, None], neighbours.shape)
    valid = (neighbours != rows) & (distances <= 2.0 * np.minimum(scales[:, None], scales[neighbours]))
    graph = coo_matrix((np.ones(np.count_nonzero(valid)), (rows[valid], neighbours[valid])), shape=(len(points), len(points)))
    _, labels = connected_components(graph, directed=False)
    order = np.argsort(labels, kind="stable")
    return np.split(order, np.flatnonzero(np.diff(labels[order])) + 1)


def _separate_layers(indices, points, normal, threshold, min_points):
    """Separate resolved parallel depth layers before spatial connectivity.

    Layers whose depth distributions overlap cannot be distinguished reliably
    here. Splits require a real residual gap and substantial support both sides.
    """
    pending, result = [(indices, 0)], []
    while pending:
        group, depth = pending.pop()
        order = np.argsort(points[group] @ normal)
        depths = points[group[order]] @ normal
        gaps = np.diff(depths)
        eligible = np.arange(len(gaps))
        valid = (eligible + 1 >= min_points) & (len(group) - eligible - 1 >= min_points)
        gaps = np.where(valid, gaps, -np.inf)
        cut = int(np.argmax(gaps)) if len(gaps) else 0
        if depth < 3 and len(gaps) and gaps[cut] > threshold * 0.5:
            pending.extend([(group[order[:cut + 1]], depth + 1), (group[order[cut + 1:]], depth + 1)])
        else:
            result.append(group)
    return result


def _fit_patch(points, indices, threshold, normals):
    indices = np.asarray(indices, dtype=np.int64)
    for _ in range(3):
        if len(indices) < 3:
            return None
        selected = points[indices]
        center = selected.mean(axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov((selected - center).T))
        # Broad measured surfaces are the first target. Narrow strips along a
        # curved pipe or beam remain residual rather than being flattened.
        if eigenvalues[-1] <= 0 or eigenvalues[1] <= eigenvalues[-1] * 0.01:
            return None
        normal = eigenvectors[:, 0]
        if normal[np.argmax(np.abs(normal))] < 0:
            normal = -normal
        offset = -float(center @ normal)
        residual = selected @ normal + offset
        keep = np.abs(residual) <= threshold
        if normals is not None:
            keep &= np.abs(normals[indices] @ normal) >= np.cos(np.deg2rad(25))
        indices = indices[keep]
        if keep.all():
            break
    if len(indices) < 3:
        return None
    residual = points[indices] @ normal + offset
    if normals is not None:
        # A coherent normal population gives additional evidence for a plane.
        # Strongly varying tangent directions should remain unmodified.
        if np.quantile(np.abs(normals[indices] @ normal), 0.2) < np.cos(np.deg2rad(15)):
            return None
    spacing = float(np.median(_local_scales(points[indices])))
    if not np.isfinite(spacing) or spacing <= 0:
        return None
    return PlanarPatch(indices, normal, offset, float(np.sqrt(np.mean(residual**2))), spacing)


def segment_planar_patches(
    cloud, *, distance_threshold: float, max_planes: int, min_points: int, seed: int = 7
) -> tuple[np.ndarray, list[PlanarPatch]]:
    """Detect connected, geometrically supported planar patches.

    ``max_planes`` bounds RANSAC proposals; one proposal can produce several
    disconnected patches. Uncertain/rejected points retain label -1. Normal
    gating does not rely on a global normal sign. Coordinates must be local.
    """
    if not np.isfinite(distance_threshold) or distance_threshold <= 0:
        raise ValueError("distance_threshold must be finite and positive")
    if not isinstance(max_planes, int) or max_planes < 0 or not isinstance(min_points, int) or min_points < 3:
        raise ValueError("max_planes must be >= 0 and min_points must be >= 3")
    points = np.asarray(cloud.points)
    labels = np.full(len(points), -1, dtype=np.int32)
    remaining = np.flatnonzero(np.isfinite(points).all(axis=1))
    normals = None
    if cloud.has_normals():
        values = np.asarray(cloud.normals).copy()
        lengths = np.linalg.norm(values, axis=1)
        valid = np.isfinite(values).all(axis=1) & (lengths > 0)
        values[valid] /= lengths[valid, None]
        values[~valid] = 0
        normals = values
    o3d.utility.random.seed(seed)
    patches = []
    for _ in range(max_planes):
        if len(remaining) < min_points:
            break
        subset = cloud.select_by_index(remaining.tolist())
        model, inliers = subset.segment_plane(
            distance_threshold=distance_threshold, ransac_n=3,
            num_iterations=750, probability=0.999,
        )
        if len(inliers) < min_points:
            break
        normal = np.asarray(model[:3], dtype=float)
        normal /= np.linalg.norm(normal)
        candidate = remaining[np.asarray(inliers, dtype=int)]
        # Retire the proposal even when it is rejected, avoiding repeated fits
        # to the same uncertain surface. Those points still remain unlabeled.
        keep = np.ones(len(remaining), dtype=bool)
        keep[inliers] = False
        remaining = remaining[keep]
        if normals is not None:
            candidate = candidate[np.abs(normals[candidate] @ normal) >= np.cos(np.deg2rad(25))]
        for layer in _separate_layers(candidate, points, normal, distance_threshold, min_points):
            for component in _connected_support(points[layer]):
                indices = layer[component]
                if len(indices) < min_points:
                    continue
                patch = _fit_patch(points, indices, distance_threshold, normals)
                if patch is not None and len(patch.indices) >= min_points:
                    labels[patch.indices] = len(patches)
                    patches.append(patch)
    return labels, patches


def mesh_planar_patch(cloud, patch: PlanarPatch) -> o3d.geometry.TriangleMesh:
    """Project within the fitted tolerance and triangulate measured support.

    Vertex order matches ``patch.indices`` exactly, including vertices unused
    after filtering. Callers can report those unused points without sending
    accepted patch boundaries through a second triangulator. No convex-hull
    completion or QHull jitter is applied.
    """
    points = np.asarray(cloud.points)[patch.indices]
    mesh = o3d.geometry.TriangleMesh()
    if len(points) < 3:
        return mesh
    normal = np.asarray(patch.normal, dtype=float)
    length = np.linalg.norm(normal)
    if not np.isfinite(normal).all() or not np.isfinite(length) or length <= 0:
        return mesh
    normal = normal / length
    projected = points - (points @ normal + patch.offset / length)[:, None] * normal
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, axis)
    u /= np.linalg.norm(u)
    basis = np.column_stack((u, np.cross(normal, u)))
    uv = (projected - projected.mean(axis=0)) @ basis
    try:
        triangles = Delaunay(uv).simplices.copy()
    except (QhullError, ValueError):
        return mesh
    scales = _local_scales(uv)
    tree = cKDTree(uv)
    a, b, c = triangles.T
    valid = np.ones(len(triangles), dtype=bool)
    for left, right in ((a, b), (b, c), (c, a)):
        valid &= np.linalg.norm(uv[left] - uv[right], axis=1) <= 2.1 * np.minimum(scales[left], scales[right])
    area = np.cross(projected[b] - projected[a], projected[c] - projected[a]) @ normal
    valid &= np.abs(area) > max(patch.spacing**2 * 1e-12, np.finfo(float).tiny)
    triangles = triangles[valid]
    barycentric = np.array([
        [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [.5, 0, .5], [0, .5, .5],
        [.5, .25, .25], [.25, .5, .25], [.25, .25, .5],
    ])
    supported = np.zeros(len(triangles), dtype=bool)
    for start in range(0, len(triangles), 4096):
        part = triangles[start:start + 4096]
        samples = np.einsum("sk,tkd->tsd", barycentric, uv[part])
        distances, nearest = tree.query(samples.reshape(-1, 2), workers=1)
        supported[start:start + len(part)] = np.all(
            (distances <= .85 * scales[nearest]).reshape(len(part), -1), axis=1
        )
    triangles = triangles[supported]
    if len(triangles) == 0:
        return mesh
    orientation = np.cross(projected[triangles[:, 1]] - projected[triangles[:, 0]], projected[triangles[:, 2]] - projected[triangles[:, 0]]) @ normal
    reverse = orientation < 0
    triangles[reverse] = triangles[reverse][:, [0, 2, 1]]
    mesh.vertices = o3d.utility.Vector3dVector(projected)
    mesh.triangles = o3d.utility.Vector3iVector(triangles)
    if cloud.has_colors():
        mesh.vertex_colors = o3d.utility.Vector3dVector(np.asarray(cloud.colors)[patch.indices])
    mesh.compute_vertex_normals()
    return mesh
