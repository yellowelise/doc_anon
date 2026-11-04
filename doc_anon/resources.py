"""Only this module accesses the network, and only on explicit setup."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

APP_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
MODEL_REVISION = 'a1c3c83827eca22e9675e30c1111c4641caf5901'
MODEL_URL = f'https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B/resolve/{MODEL_REVISION}/'
MODEL_FILES = [
    ('config.json', 3137, 'git', '86978e4bd6dfd9b0477d6ff2727805c71080df65'),
    ('special_tokens_map.json', 1051, 'git', 'be4ad795f49075ac5e56d8108ef63be314a1e967'),
    ('tokenizer_config.json', 46469, 'git', 'b002fb8c2960be8ebf9c373d6e5784b4565d7edc'),
    ('tokenizer.json', 34363286, 'sha256', 'a0ab5772a8c5450f45a66c95985d6df2205bf09449ba7ff7bb46de034eaa118a'),
    ('model.safetensors', 1230273700, 'sha256', 'b1e046e3aec52c3cd74eaf166b034644a4dac0c91128bf06803e1478657fcd9f'),
]
OCR_URL = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/ita.traineddata'
OCR_SHA = 'b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827'


class Cancelled(Exception):
    """Cooperative cancellation, never reported as an application failure."""


def data_root():
    if os.environ.get('DOC_ANON_DATA_DIR'):
        return Path(os.environ['DOC_ANON_DATA_DIR']).resolve()
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'DocAnon'


def model_dir():
    return data_root() / ('rizzo-' + MODEL_REVISION[:12])


def digest(path, kind='sha256'):
    h = hashlib.sha1() if kind == 'git' else hashlib.sha256()
    if kind == 'git':
        h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def tesseract_path():
    bundled = APP_ROOT / 'vendor/tesseract/tesseract.exe'
    return str(bundled) if bundled.is_file() else shutil.which('tesseract')


def configure_offline():
    # Even if a dependency tries a Hub lookup, it must fail locally.
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                      HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                      TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2',
                      TESSDATA_PREFIX=str(data_root() / 'tessdata'))
    if exe := tesseract_path():
        os.environ['DOC_ANON_TESSERACT'] = exe


def is_ready():
    try:
        receipt = json.loads((data_root() / 'ready.json').read_text('utf-8'))
        return (receipt['revision'] == MODEL_REVISION and bool(tesseract_path())
                and (data_root() / 'tessdata/ita.traineddata').is_file()
                and all((model_dir() / name).stat().st_size == size for name, size, _, _ in MODEL_FILES))
    except (OSError, ValueError, KeyError):
        return False


def verify_resources(progress=lambda *_: None):
    for i, (name, size, kind, expected) in enumerate(MODEL_FILES):
        progress('Verifica risorse locali…', i, len(MODEL_FILES) + 1)
        path = model_dir() / name
        if not path.is_file() or path.stat().st_size != size or digest(path, kind) != expected:
            raise RuntimeError('Modello incompleto o danneggiato. Apri Risorse e ripeti la preparazione.')
    if digest(data_root() / 'tessdata/ita.traineddata') != OCR_SHA:
        raise RuntimeError('Modello OCR danneggiato. Ripeti la preparazione delle risorse.')
    configure_offline()
    from .ocr import check_engine
    check_engine.cache_clear()
    check_engine()


def download(url, destination, expected, kind='sha256', size=None, progress=lambda *_: None):
    """Pinned, streamed downloads; resumes interrupted large files, verifies before rename."""
    import requests
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and digest(destination, kind) == expected:
        progress(destination.name, size or destination.stat().st_size, size or destination.stat().st_size)
        return
    part = destination.with_suffix(destination.suffix + '.part')
    if part.is_file() and (size is None or part.stat().st_size >= size):
        if digest(part, kind) == expected:
            part.replace(destination)
            return
        part.unlink()
    for attempt in range(3):
        progress('Connessione per ' + destination.name, 0, size or 0)
        offset = part.stat().st_size if part.exists() else 0
        try:
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            with requests.get(url, headers=headers, stream=True, timeout=(15, 30)) as response:
                response.raise_for_status()
                if offset and response.status_code == 206:
                    if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise RuntimeError('Risposta download non valida.')
                else:
                    offset = 0
                total = size or offset + int(response.headers.get('Content-Length', 0))
                done = offset
                with part.open('ab' if offset else 'wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        progress(destination.name, done, total)
                        if not chunk:
                            continue
                        stream.write(chunk)
                        done += len(chunk)
                        if size and done > size:
                            raise RuntimeError('Dimensione download inattesa.')
                progress('Verifica ' + destination.name, done, total)
            if (size and part.stat().st_size != size) or digest(part, kind) != expected:
                part.unlink(missing_ok=True)
                raise RuntimeError('Verifica del download fallita. Riprova la preparazione.')
            part.replace(destination)
            return
        except requests.RequestException as exc:
            if attempt == 2:
                raise RuntimeError('Download interrotto. Controlla Internet e riprova: il trasferimento riprenderà.') from exc
            time.sleep(1)


def prepare(progress=lambda *_: None):
    data_root().mkdir(parents=True, exist_ok=True)
    if not tesseract_path():
        raise RuntimeError('Motore OCR assente. Usa la distribuzione completa di Doc Anon.')
    required = sum(size for name, size, _, _ in MODEL_FILES if not (model_dir() / name).is_file())
    if shutil.disk_usage(data_root()).free < required + 256 * 1024 * 1024:
        raise RuntimeError('Spazio insufficiente: libera almeno 1,6 GB per il modello.')
    for name, size, kind, expected in MODEL_FILES:
        download(MODEL_URL + name, model_dir() / name, expected, kind, size, progress)
    download(OCR_URL, data_root() / 'tessdata/ita.traineddata', OCR_SHA, progress=progress)
    verify_resources(progress)
    receipt = data_root() / 'ready.json'
    tmp = receipt.with_suffix('.tmp')
    tmp.write_text(json.dumps({'revision': MODEL_REVISION, 'format': 1}), encoding='utf-8')
    tmp.replace(receipt)
    progress('Pronto per lavorare offline', 1, 1)
