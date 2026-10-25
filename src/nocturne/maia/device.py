"""Select an available accelerator; inference is the final capability probe."""
import os


def select_device(torch):
    if os.environ.get('NOCTURNE_MAIA_DEVICE') == 'cpu':
        return torch.device('cpu'), 'CPU (selected)'
    try:
        if torch.cuda.is_available():
            device = torch.device('cuda:0')
            name = torch.cuda.get_device_name(0)
            backend = 'AMD ROCm' if getattr(torch.version, 'hip', None) else 'NVIDIA CUDA'
            return device, f'{backend} · {name}'
    except Exception:
        pass
    try:
        import torch_directml
        if torch_directml.device_count():
            return torch_directml.device(), f'DirectML · {torch_directml.device_name(0)}'
    except (ImportError, RuntimeError, OSError):
        pass
    return torch.device('cpu'), 'CPU · no compatible GPU runtime'
