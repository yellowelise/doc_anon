from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules

root = Path(SPECPATH)
datas = [(str(root / 'vendor'), 'vendor'), (str(root / 'assets'), 'assets'), (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
datas += collect_data_files('transformers')
for package in ['transformers', 'torch', 'safetensors', 'tokenizers', 'huggingface-hub', 'regex', 'requests', 'numpy', 'packaging', 'tqdm', 'filelock', 'pyyaml']:
    datas += copy_metadata(package)
hidden = ['transformers.models.modernbert.modeling_modernbert', 'transformers.models.modernbert.configuration_modernbert',
          'transformers.tokenization_utils_fast', 'transformers.models.auto.tokenization_auto',
          'transformers.models.auto.configuration_auto', 'transformers.models.auto.modeling_auto']
a = Analysis(['main.py'], pathex=[str(root)], binaries=[], datas=datas, hiddenimports=hidden,
             hookspath=[], runtime_hooks=[], excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'matplotlib', 'scipy',
             'pandas', 'sklearn', 'tensorflow', 'jax', 'torchaudio', 'torchvision', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DocAnon', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets/doc-anon.ico'),
          version=str(root / 'version-info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DocAnon')
