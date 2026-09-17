import os

import ndicapy

# Fields fixed by the NDI protocol (see ndicapi.h):
# num(8) sys(1) tool(1) port(2) chan(2). tool="1" = wireless tool (passive spheres).
PHRQ_WIRELESS = "PHRQ:" + "*" * 8 + "*" + "1" + "**" + "**"


class PolarisTracker:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.device = None
        self.handles = {}  # rom filename -> port handle

    def connect(self):
        self.device = ndicapy.ndiOpenNetwork(self.host, self.port)
        if self.device is None:
            raise RuntimeError(f"Could not connect to {self.host}:{self.port}")

        api_rev = ndicapy.ndiCommand(self.device, "APIREV:")
        self._check("APIREV")

        ndicapy.ndiCommand(self.device, "INIT:")
        self._check("INIT")

        return api_rev

    def _check(self, step):
        err = ndicapy.ndiGetError(self.device)
        if err:
            raise RuntimeError(f"{step}: {ndicapy.ndiErrorString(err)}")

    def load_tool(self, rom_path):
        """Requests a port handle and loads a wireless passive tool's geometry into it."""
        ndicapy.ndiCommand(self.device, PHRQ_WIRELESS)
        self._check("PHRQ")
        handle = ndicapy.ndiGetPHRQHandle(self.device)

        ndicapy.ndiPVWRFromFile(self.device, handle, rom_path)
        self._check(f"PVWR {os.path.basename(rom_path)}")

        ndicapy.ndiCommand(self.device, f"PINIT:{handle:02X}")
        self._check(f"PINIT {handle:02X}")

        ndicapy.ndiCommand(self.device, f"PENA:{handle:02X}D")
        self._check(f"PENA {handle:02X}")

        self.handles[os.path.basename(rom_path)] = handle
        return handle

    def start_tracking(self):
        ndicapy.ndiCommand(self.device, "TSTART:")
        self._check("TSTART")

    def stop_tracking(self):
        ndicapy.ndiCommand(self.device, "TSTOP:")
        self._check("TSTOP")

    def get_positions(self):
        """Returns {rom filename: transform or None if out of view}.

        transform is (q0, qx, qy, qz, tx, ty, tz, error).
        """
        ndicapy.ndiCommand(self.device, "TX:0001")
        self._check("TX")
        return self._read_positions()

    def get_stray_markers(self):
        """Returns a list of (x, y, z) coordinates for every reflective
        marker currently visible to the camera that isn't already claimed
        by one of the loaded/enabled tools.

        The Polaris only runs its passive-marker detection engine while at
        least one passive port is enabled, so at least one tool must be
        loaded (see load_tool()) even though its own markers won't show up
        here.
        """
        ndicapy.ndiCommand(self.device, "TX:9001")
        self._check("TX")
        return self._read_stray_markers()

    def read_frame(self):
        """Like calling get_positions() and get_stray_markers() together,
        but in a single TX query instead of two -- needed to keep up with
        high capture rates (e.g. 30 Hz).

        Returns (positions, stray_markers).
        """
        ndicapy.ndiCommand(self.device, "TX:9001")
        self._check("TX")
        return self._read_positions(), self._read_stray_markers()

    def _read_positions(self):
        positions = {}
        for name, handle in self.handles.items():
            transform = ndicapy.ndiGetTXTransform(self.device, bytes([handle]))
            positions[name] = None if transform == "MISSING" else transform
        return positions

    def _read_stray_markers(self):
        n = ndicapy.ndiGetTXNumberOfPassiveStrays(self.device)
        coords = [ndicapy.ndiGetTXPassiveStray(self.device, i) for i in range(n)]
        # A marker that drops out of view right as the frame is read is
        # still counted by the device, but its coordinates come back as a
        # (0, 0, 0) placeholder instead of real data -- drop those.
        return [c for c in coords if c != (0.0, 0.0, 0.0)]

    def release_tool(self, handle):
        ndicapy.ndiCommand(self.device, f"PDIS:{handle:02X}")
        ndicapy.ndiCommand(self.device, f"PHF:{handle:02X}")

    def unload_tool(self, rom_path):
        """Releases a tool previously loaded with load_tool()."""
        name = os.path.basename(rom_path)
        handle = self.handles.pop(name)
        self.release_tool(handle)

    def close(self):
        for handle in list(self.handles.values()):
            self.release_tool(handle)
        self.handles.clear()

        if self.device is not None:
            ndicapy.ndiClose(self.device)
            self.device = None