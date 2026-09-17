import argparse
import csv
import itertools
import os
import time

import numpy as np

from ndi_utils import PolarisTracker

ROMS_DIR = os.path.join(os.path.dirname(__file__), "roms")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute the rigid transform between the sensor and world frames."
    )
    parser.add_argument("--host", required=True, help="Polaris host address")
    parser.add_argument("--port", type=int, required=True, help="Polaris port")
    parser.add_argument(
        "--rom",
        dest="rom",
        required=True,
        help="ROM file name to load, relative to the roms/ directory. Loaded only to enable "
        "the Polaris' passive-marker detection engine (it needs at least one enabled tool "
        "port to report stray markers at all); this tool's own tracked pose is never read.",
    )
    parser.add_argument(
        "--world-positions-csv",
        default=os.path.join(os.path.dirname(__file__), "world_positions.csv"),
        help="CSV file with the known marker positions in the world frame (default: %(default)s)",
    )
    parser.add_argument(
        "--output-path",
        default=os.path.join(os.path.dirname(__file__), "sensor_to_world_transform"),
        help="Output path (without extension) for the computed transform (default: %(default)s)",
    )
    return parser.parse_args()


def load_world_positions(csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        return np.array(
            [[float(row["x_mm"]), float(row["y_mm"]), float(row["z_mm"])] for row in reader]
        )


def match_points(world_points, sensor_points):
    """Finds which detected sensor point corresponds to which world row.

    The Polaris reports stray markers in arbitrary detection order, so
    correspondence is recovered by finding the permutation of sensor points
    whose pairwise distances best match the world points' pairwise distances
    -- those distances are invariant to the rigid transform being solved for.
    """
    n = len(world_points)
    world_dists = np.linalg.norm(world_points[:, None] - world_points[None, :], axis=-1)

    best_perm, best_cost = list(range(n)), np.inf
    for perm in itertools.permutations(range(n)):
        candidate = sensor_points[list(perm)]
        cand_dists = np.linalg.norm(candidate[:, None] - candidate[None, :], axis=-1)
        cost = np.sum((cand_dists - world_dists) ** 2)
        if cost < best_cost:
            best_cost, best_perm = cost, list(perm)
    return best_perm, best_cost


def rigid_transform(source_points, target_points):
    """Kabsch algorithm: least-squares rotation + translation mapping source -> target."""
    source_centroid = source_points.mean(axis=0)
    target_centroid = target_points.mean(axis=0)
    H = (source_points - source_centroid).T @ (target_points - target_centroid)

    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))  # guards against a reflection instead of a rotation
    R = Vt.T @ np.diag([1, 1, d]) @ U.T
    t = target_centroid - R @ source_centroid

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def main():
    args = parse_args()
    world_points = load_world_positions(args.world_positions_csv)
    rom_path = os.path.join(ROMS_DIR, args.rom)
    if not os.path.isfile(rom_path):
        print(f"ROM file not found: {rom_path}")
        return

    print(f"Connecting to {args.host}:{args.port}...")
    tracker = PolarisTracker(args.host, args.port)
    api_rev = tracker.connect()
    print(f"Connection established. API revision: {api_rev}")

    try:
        tracker.load_tool(rom_path)
        print(f"Tool loaded: {args.rom} (used only to enable marker detection)")
        tracker.start_tracking()
        time.sleep(0.5)  # let the camera settle before the single capture

        positions, stray = tracker.read_frame()
        tracker.stop_tracking()

        tool_transform = positions.get(args.rom)
        tool_pos_sensor = np.array(tool_transform[4:7]) if tool_transform is not None else None

        print(f"Captured {len(stray)} marker(s), expected {len(world_points)}.")
        if len(stray) != len(world_points):
            print(
                "Marker count mismatch -- make sure only the world markers are "
                "visible to the camera (no other reflective spheres) and try again."
            )
            return

        sensor_points = np.array(stray)
        perm, cost = match_points(world_points, sensor_points)
        matched_sensor_points = sensor_points[perm]

        print("Matched correspondences (world row <-> sensor point):")
        for i, (wp, sp) in enumerate(zip(world_points, matched_sensor_points)):
            print(f"  world[{i}] {wp} <-> sensor {sp}")
        print(f"Matching cost (pairwise-distance residual, mm^2): {cost:.4f}")

        T_world_from_sensor = rigid_transform(matched_sensor_points, world_points)
        T_sensor_from_world = np.linalg.inv(T_world_from_sensor)

        predicted = (T_world_from_sensor[:3, :3] @ matched_sensor_points.T).T + T_world_from_sensor[:3, 3]
        rmse = np.sqrt(np.mean(np.sum((predicted - world_points) ** 2, axis=1)))
        print(f"Registration RMSE: {rmse:.3f} mm")

        np.set_printoptions(precision=6, suppress=True)
        print("\nT_world_from_sensor (maps a point from the sensor frame to the world frame):")
        print(T_world_from_sensor)
        print("\nT_sensor_from_world (maps a point from the world frame to the sensor frame):")
        print(T_sensor_from_world)

        np.savetxt(args.output_path + ".txt", T_world_from_sensor, fmt="%.6f")
        print(f"\nSaved T_world_from_sensor to {args.output_path}.txt")

        if tool_pos_sensor is not None:
            tool_pos_world = T_world_from_sensor[:3, :3] @ tool_pos_sensor + T_world_from_sensor[:3, 3]
            print(
                f"\n{args.rom} position in the world frame (verification): "
                f"({tool_pos_world[0]:.2f}, {tool_pos_world[1]:.2f}, {tool_pos_world[2]:.2f}) mm"
            )
        else:
            print(f"\n{args.rom} was out of camera view during the capture -- no verification position.")

    finally:
        tracker.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
