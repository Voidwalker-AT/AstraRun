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
    # Example 3D function: z = sin(sqrt(x^2 + y^2))
    x = y = -10
    step = 0.1
    width, height = 400, 400
    rgb_bytes = bytearray(width * height * 3)

    for y in range(height):
        for x in range(width):
            z = math.sin(math.sqrt(x**2 + y**2))
            val = max(0, min(255, int(127.5 * (z + 1.0))))
            rgb_bytes[y * width * 3 + x * 3] = val
            rgb_bytes[y * width * 3 + x * 3 + 1] = val
            rgb_bytes[y * width * 3 + x * 3 + 2] = 255

    save_png('3d_visualization.png', width, height, rgb_bytes)

def main():
    os.environ['ASTRARUN_OUTPUT_DIR'] = os.path.join(os.path.expanduser('~'), 'Desktop')
    generate_3d_visualization()
    print('3D visualization generated and saved to Desktop.')

if __name__ == "__main__":
    main()