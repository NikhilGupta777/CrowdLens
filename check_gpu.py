import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU memory: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")
else:
    print("NO GPU DETECTED BY PYTORCH")
    print(f"CUDA built with: {torch.version.cuda}")

# Check onnxruntime
try:
    import onnxruntime as ort
    print(f"\nONNX Runtime version: {ort.__version__}")
    print(f"Available providers: {ort.get_available_providers()}")
except Exception as e:
    print(f"\nONNX Runtime error: {e}")

# Check nvidia-smi
import subprocess
try:
    result = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"\nnvidia-smi: {result.stdout.strip()}")
    else:
        print(f"\nnvidia-smi failed: {result.stderr}")
except Exception as e:
    print(f"\nnvidia-smi not found: {e}")
