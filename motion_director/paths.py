import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def input_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if path.suffix.lower() not in (".glb", ".gltf"):
        raise ValueError("MVP input must be .glb or .gltf")
    return path


def output_paths(source: Path, directory: Path) -> dict[str, Path]:
    directory = directory.expanduser().resolve()
    paths = {
        "model": directory / f"{source.stem}_spear_throw.glb",
        "metadata": directory / "spear_throw.motion.json",
        "report": directory / "spear_throw_report.md",
        "recipe": directory / "spear_throw.blender.py",
        "job": directory / "spear_throw.job.json",
        "preview": directory / "spear_throw_preview.mp4",
        "poses": directory / "spear_throw_poses.png",
    }
    for path in paths.values():
        if path.resolve() == source.resolve():
            raise ValueError("Refusing to overwrite the input model")
        if path.exists():
            raise FileExistsError(
                f"Output already exists: {path}. Choose a new --output directory."
            )
    return paths
