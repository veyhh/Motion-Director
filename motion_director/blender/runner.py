import json
import subprocess
import tempfile
from pathlib import Path


def run_blender(blender: Path, job: dict, timeout: int = 300) -> dict:
    """JSON is data, never interpolated into executable Python or shell commands."""
    with tempfile.TemporaryDirectory(prefix="motion-director-") as temp:
        directory = Path(temp)
        request, response = directory / "job.json", directory / "result.json"
        request.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        entry = Path(__file__).with_name("entry.py")
        command = [
            str(blender),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(entry),
            "--",
            str(request),
            str(response),
        ]
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        result = json.loads(response.read_text(encoding="utf-8")) if response.exists() else {}
        if process.returncode or result.get("error") or not result:
            raise RuntimeError(
                result.get("error")
                or process.stderr[-3000:]
                or process.stdout[-3000:]
                or "Blender returned no result"
            )
        result["blender_log"] = process.stdout[-10000:]
        return result
