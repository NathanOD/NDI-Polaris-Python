import argparse
import csv
import os
import time
from datetime import datetime, timezone

from ndi_utils import PolarisTracker

ROMS_DIR = os.path.join(os.path.dirname(__file__), "roms")


def parse_args():
    parser = argparse.ArgumentParser(description="Record tracked tool and stray marker positions to a CSV file.")
    parser.add_argument("--host", required=True, help="Polaris host address")
    parser.add_argument("--port", type=int, required=True, help="Polaris port")
    parser.add_argument(
        "--rom",
        dest="roms",
        action="append",
        required=True,
        help="ROM file name to load, relative to the roms/ directory. Can be passed multiple times.",
    )
    parser.add_argument(
        "--frequency",
        type=float,
        default=30,
        help="Refresh frequency in Hz (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=15,
        help="Recording duration in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--output-csv",
        default=os.path.join(os.path.dirname(__file__), "positions.csv"),
        help="Output CSV file path (default: %(default)s)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    frame_period_s = 1 / args.frequency
    nb_readings = int(args.frequency * args.duration)
    rom_paths = [os.path.join(ROMS_DIR, name) for name in args.roms]
    missing = [p for p in rom_paths if not os.path.isfile(p)]
    if missing:
        print(f"ROM file(s) not found: {missing}")
        return

    print(f"Connecting to {args.host}:{args.port}...")
    tracker = PolarisTracker(args.host, args.port)
    api_rev = tracker.connect()
    print(f"Connection established. API revision: {api_rev}")

    try:
        for rom_path in rom_paths:
            tracker.load_tool(rom_path)
            print(f"Tool loaded: {os.path.basename(rom_path)}")

        tracker.start_tracking()

        with open(args.output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame", "timestamp", "label", "x_mm", "y_mm", "z_mm"])

            next_frame_time = time.monotonic()

            for i in range(nb_readings):
                timestamp = datetime.now(timezone.utc).isoformat()

                positions, stray_markers = tracker.read_frame()
                log = i % int(args.frequency) == 0  # console logs limited to 1/s, CSV keeps every frame

                # Every known tool always gets a row -- a real position, or a
                # 0,0,0 placeholder when it's out of view -- so it can't be
                # silently dropped just because other balls were detected.
                for name, transform in positions.items():
                    if transform is not None:
                        _, _, _, _, tx, ty, tz, _ = transform
                        writer.writerow([i, timestamp, name, f"{tx:.2f}", f"{ty:.2f}", f"{tz:.2f}"])
                        if log:
                            print(f"[{i}] {name}: position=({tx:.2f}, {ty:.2f}, {tz:.2f}) mm")
                    else:
                        writer.writerow([i, timestamp, name, "0.00", "0.00", "0.00"])
                        if log:
                            print(f"[{i}] {name}: out of camera view")

                for j, (x, y, z) in enumerate(stray_markers):
                    writer.writerow([i, timestamp, f"extra_{j}", f"{x:.2f}", f"{y:.2f}", f"{z:.2f}"])
                    if log:
                        print(f"[{i}] extra_{j}: position=({x:.2f}, {y:.2f}, {z:.2f}) mm")

                next_frame_time += frame_period_s
                sleep_time = next_frame_time - time.monotonic()
                if sleep_time > 0:
                    time.sleep(sleep_time)

        tracker.stop_tracking()
        print(f"Positions saved to {args.output_csv}")

    finally:
        tracker.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
