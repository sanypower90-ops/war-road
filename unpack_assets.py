from pathlib import Path
from zipfile import ZipFile
root=Path(__file__).resolve().parent
for pack in sorted(root.glob("assetpack-*.zip")):
    with ZipFile(pack) as z:
        for name in z.namelist():
            target=(root/name).resolve()
            if not target.is_relative_to(root):raise ValueError("Invalid asset path")
        z.extractall(root)
    print("Unpacked",pack.name)
