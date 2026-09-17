# NDI-Polaris-Python

Python scripts to track tools and markers with an NDI Polaris sensor.

## Installation

```shell
conda create -n polaris python=3.12
conda activate polaris
pip install ndicapi
```

## Setup

- Find your sensor's IP address and port.
- Get the ROM files for your tools and put them in the `roms` folder.

## Usage

### Track tools

Print the position and orientation of one or more known tools.

```shell
python track_tools.py --host <IP> --port <PORT> --rom <ROM_FILE_1> --rom <ROM_FILE_2> --nb-scans 100 --frequency 30
```

### Track tools and stray markers

Print known tool positions plus any unmatched ("stray") marker. You must give at least one ROM file, otherwise the sensor won't let you scan even if the tool isn't physically present.

```shell
python track_markers.py --host <IP> --port <PORT> --rom <ROM_FILE_1> --nb-scans 100 --frequency 30
```

### Record tools and markers

Same as above, but writes every frame to a CSV file (same ROM constraint applies).

```shell
python record_markers.py --host <IP> --port <PORT> --rom <ROM_FILE_1> --duration 15 --frequency 30 --output-csv scan.csv
```

### Compute the sensor-to-table transform

Place markers in the field of view, note their positions in a CSV file, then compute the rigid transform between the sensor and table frames.

```shell
python get_trans_matrix.py --host <IP> --port <PORT> --rom <ROM_FILE_1> --table-positions-csv positions.csv --output-path transformation
```
