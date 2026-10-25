"""Optional Windows GPU setup, isolated from the bundled CPU runtime."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('source', type=Path)
    parser.add_argument('checkpoint', type=Path)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or sys.platform != 'win32':
        raise RuntimeError('Install Python 3.12 x64 from python.org to set up GPU acceleration.')
    inventory = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        'Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name'],
        text=True, errors='replace', timeout=30).lower()
    nvidia = 'nvidia' in inventory
    amd = 'amd' in inventory or 'radeon' in inventory
    if not nvidia and not amd:
        raise RuntimeError('No NVIDIA or AMD adapter detected. The bundled CPU runtime remains available.')
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / 'ready.json'
    marker.unlink(missing_ok=True)
    print('Creating isolated GPU environment. This may download several GB.', flush=True)
    venv.create(root, with_pip=True, clear=True)
    python = root / 'Scripts/python.exe'
    if nvidia:
        packages = ['torch==2.7.1', '--index-url', 'https://download.pytorch.org/whl/cu128']
        subprocess.run([str(python), '-m', 'pip', 'install', *packages], check=True)
    else:
        print('Installing native AMD ROCm 7.2.1 / PyTorch 2.9.1. AMD requires graphics driver 26.2.2. '
              'Unsupported adapters will keep using the bundled CPU runtime.', flush=True)
        repo = 'https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/'
        sdk = [repo + name for name in (
            'rocm_sdk_core-7.2.1-py3-none-win_amd64.whl',
            'rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl',
            'rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl',
            'rocm-7.2.1.tar.gz')]
        subprocess.run([str(python), '-m', 'pip', 'install', *sdk], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install',
                        repo + 'torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', 'numpy==1.26.4', 'python-chess==1.999'], check=True)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(args.source.resolve())
    env['NOCTURNE_MAIA_DEVICE'] = 'auto'
    probe = '''import json,sys
from nocturne.maia.worker import Predictor
p=Predictor(sys.argv[1])
p.predict("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [], [1800])
print(json.dumps({"device":p.device_label,"gpu":p.device.type!="cpu"}))
'''
    result = subprocess.run([str(python), '-c', probe, str(args.checkpoint.resolve())],
                            env=env, capture_output=True, text=True, timeout=240, check=True)
    info = json.loads(result.stdout.strip().splitlines()[-1])
    if not info['gpu']:
        raise RuntimeError('GPU model probe failed: ' + info['device'] + '. CPU remains available.')
    marker.write_text(json.dumps(info), encoding='utf-8')
    print('Ready: ' + info['device'], flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GPU setup stopped: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
