import argparse
import os
import time

from ndi_utils import PolarisTracker

ROMS_DIR = os.path.join(os.path.dirname(__file__), "roms")


def parse_args():
    parser = argparse.ArgumentParser(description="Track known tools and report stray markers.")
    parser.add_argument("--host", required=True, help="Polaris host address")
    parser.add_argument("--port", type=int, required=True, help="Polaris port")
    parser.add_argument(
        "--rom",
        dest="roms",
        action="append",
        required=True,
        help="ROM file name to load, relative to the roms/ directory. Can be passed multiple times. "
        "The Polaris only detects passive markers while at least one tool port is enabled, "
        "and any marker matched to a loaded tool's known geometry stops showing up as stray. "
        "Loading every distinct rom at once (instead of swapping one at a time) means each "
        "known shape claims at most one physical instance of itself -- any extra ball, "
        "including a duplicate of an already-loaded shape, is left over and reported as "
        "stray exactly once.",
    )
    parser.add_argument(
        "--nb-scans",
        type=int,
        default=100,
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
            known = tracker.get_positions()
            stray = tracker.get_stray_markers()

            n_known = sum(1 for t in known.values() if t is not None)
            print(f"[{i}] {n_known} known tool(s) tracked, {len(stray)} extra ball(s):")
            for name, transform in known.items():
                if transform is not None:
                    _, _, _, _, tx, ty, tz, _ = transform
                    print(f"    {name}: position=({tx:.2f}, {ty:.2f}, {tz:.2f}) mm")
            for j, (x, y, z) in enumerate(stray):
                print(f"    extra ball {j}: position=({x:.2f}, {y:.2f}, {z:.2f}) mm")

            time.sleep(frame_period_s)

        tracker.stop_tracking()

    finally:
        tracker.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
