from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1] / 'vendor/licenses'
root.mkdir(parents=True, exist_ok=True)
for distribution in distributions():
    name = distribution.metadata['Name']
    for file in distribution.files or []:
        path = Path(file)
        if any(word in path.name.lower() for word in ('license', 'copying', 'notice')):
            source = Path(distribution.locate_file(file))
            if source.is_file() and source.suffix.lower() not in {'.py', '.pyc', '.pyd', '.dll'}:
                destination = root / name / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and destination.read_bytes() != source.read_bytes():
                    destination = destination.with_name(str(len(list(destination.parent.iterdir()))) + '-' + path.name)
                shutil.copy2(source, destination)
