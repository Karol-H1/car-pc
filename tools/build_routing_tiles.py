"""Build Valhalla's offline routing data from an OpenStreetMap extract (.osm.pbf).

Usage:  python tools/build_routing_tiles.py path/to/region.osm.pbf
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import valhalla

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import navigation  # noqa: E402

IS_WINDOWS = platform.system() == "Windows"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pbf = Path(sys.argv[1]).resolve()

    tiles = config.ROUTING_TILES
    if tiles.exists():
        shutil.rmtree(tiles)
    tiles.mkdir(parents=True)

    config_path = config.DATA_DIR / "valhalla.json"
    config_path.write_text(json.dumps(navigation.routing_config(), indent=2))

    package_dir = Path(valhalla.__file__).parent
    builder = package_dir / "bin" / ("valhalla_build_tiles.exe" if IS_WINDOWS else "valhalla_build_tiles")
    env = os.environ.copy()
    if IS_WINDOWS:
        # pyvalhalla's own launcher fails on Windows, so run the builder directly
        # with the folder of DLLs it depends on added to PATH.
        env["PATH"] = str(package_dir.parent / "pyvalhalla.libs") + os.pathsep + env["PATH"]

    started = time.time()
    print(f"Building routing tiles from {pbf} (a big state can take several minutes) ...")
    subprocess.run([str(builder), "-c", str(config_path), str(pbf)], env=env, check=True,
                   stdout=subprocess.DEVNULL)
    print(f"Done in {time.time() - started:.0f}s: {tiles}")


if __name__ == "__main__":
    main()
