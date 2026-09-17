import argparse
import os
import time

from ndi_utils import PolarisTracker

ROMS_DIR = os.path.join(os.path.dirname(__file__), "roms")


def parse_args():
    parser = argparse.ArgumentParser(description="Track NDI Polaris tools and print their positions.")
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
        "--nb-scans",
        type=int,
        default=70,
        help="Number of scans to perform (default: %(default)s)",
    )
    parser.add_argument(
        "--frequency",
        type=float,
        default=30,
        help="Refresh frequency in Hz (default: %(default)s)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    frame_period_s = 1 / args.frequency
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

        for i in range(args.nb_scans):
            for name, transform in tracker.get_positions().items():
                if transform is None:
                    print(f"[{i}] {name}: out of camera view")
                else:
                    q0, qx, qy, qz, tx, ty, tz, error = transform
                    print(
                        f"[{i}] {name}: "
                        f"position=({tx:.2f}, {ty:.2f}, {tz:.2f}) mm, "
                        f"quaternion=({q0:.4f}, {qx:.4f}, {qy:.4f}, {qz:.4f}), "
                        f"error={error:.4f} mm"
                    )
            time.sleep(frame_period_s)

        tracker.stop_tracking()

    finally:
        tracker.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
