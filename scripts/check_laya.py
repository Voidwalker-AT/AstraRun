import sys
print("Python:", sys.version)

try:
    import torch
    print("Torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("Device name:", torch.cuda.get_device_name(0))
except Exception as e:
    print("Torch error:", e)

try:
    import transformers
    print("Transformers:", transformers.__version__)
except Exception as e:
    print("Transformers error:", e)

try:
    import laya
    print("Laya imported successfully:", dir(laya))
except Exception as e:
    print("Laya error:", e)
