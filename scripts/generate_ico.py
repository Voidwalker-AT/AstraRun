"""Generate multi-resolution Windows .ico file for AstraRun."""

import math
from pathlib import Path
from PIL import Image, ImageDraw

def draw_astra_star(size: int) -> Image.Image:
    """Draw a crisp antialiased Astra 4-point star on transparent background."""
    scale = 4  # 4x supersampling for ultra crisp edges
    w = size * scale
    h = size * scale
    
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Optional rounded squircle or transparent background
    # We do a subtle dark squircle background for larger icons
    pad = int(w * 0.05)
    r = int(w * 0.22)
    # Background: #141519 with #282a32 border
    draw.rounded_rectangle(
        [pad, pad, w - pad, h - pad],
        radius=r,
        fill=(20, 21, 25, 255),
        outline=(40, 42, 50, 255),
        width=max(1, int(scale * 1.5))
    )
    
    # Astra 4-point star in center
    cx = w / 2.0
    cy = h / 2.0
    r_outer = w * 0.38
    r_inner = w * 0.09
    
    points = []
    for i in range(8):
        angle = i * (math.pi / 4.0) - (math.pi / 2.0)
        r_curr = r_outer if (i % 2 == 0) else r_inner
        x = cx + r_curr * math.cos(angle)
        y = cy + r_curr * math.sin(angle)
        points.append((x, y))
        
    # Fill star with cool Astra accent #5b8cf7
    draw.polygon(points, fill=(91, 140, 247, 255))
    
    # Downsample with Lanczos filter for smooth antialiasing
    return img.resize((size, size), Image.Resampling.LANCZOS)

def main():
    out_dir = Path("resources/icons")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_astra_star(s) for s in sizes]
    
    # Save multi-size .ico
    ico_path = out_dir / "AstraRun.ico"
    images[-1].save(
        str(ico_path),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1]
    )
    
    # Also save a 256x256 PNG for installer branding
    png_path = out_dir / "AstraRun.png"
    images[-1].save(str(png_path), format="PNG")
    
    print(f"Generated {ico_path} ({ico_path.stat().st_size:,} bytes) with sizes {sizes}")
    print(f"Generated {png_path} ({png_path.stat().st_size:,} bytes)")

if __name__ == "__main__":
    main()
