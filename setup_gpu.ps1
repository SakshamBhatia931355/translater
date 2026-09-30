$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.12 virtual environment.' }
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip.' }

& $python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'Could not install the CUDA 12.8 PyTorch build.' }

& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the project dependencies.' }

& $python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not detected')"
