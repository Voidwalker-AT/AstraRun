import os
import sys
import math
import struct
import zlib
import json
import re
from pathlib import Path

def save_png(filename, width, height, rgb_bytes):
    import zlib, struct
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgb_bytes[y * width * 3 : (y + 1) * width * 3])
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(filename, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))

def generate_3d_visualization():
    # Choose a function to visualize
    def f(x, y):
        return math.sin(math.hypot(x, y))

    # Define the domain
    x_min, x_max = -10, 10
    y_min, y_max = -10, 10
    width = 400
    height = 400

    # Generate the 3D surface
    rgb_bytes = bytearray()
    for y in range(height):
        for x in range(width):
            z = f(x / width * (x_max - x_min) + x_min, y / height * (y_max - y_min) + y_min)
            val = max(0, min(255, int(127.5 * (z + 1.0))))
            rgb_bytes.extend(struct.pack('>BBB', val, val, 255))

    # Save the 3D visualization
    output_dir = os.environ.get('ASTRARUN_OUTPUT_DIR', '.')
    output_path = Path(output_dir) / '3d_visualization.png'
    save_png(output_path, width, height, rgb_bytes)

    # Print the result to stdout
    print(f'3D visualization saved to {output_path}')

if __name__ == '__main__':
    generate_3d_visualization()