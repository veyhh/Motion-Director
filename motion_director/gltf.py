"""Small standard-library glTF reader for independently checking exported clips."""

import base64
import json
import math
import struct
from pathlib import Path
from urllib.parse import unquote

from motion_director.motion.validation import validate_plan


def read_gltf(path: Path):
    data = path.read_bytes()
    binary = None
    if path.suffix.lower() == ".glb":
        if len(data) < 20:
            raise ValueError("Truncated GLB")
        magic, version, length = struct.unpack_from("<4sII", data)
        if magic != b"glTF" or version != 2 or length != len(data):
            raise ValueError("Invalid GLB header or length")
        offset, document = 12, None
        while offset < len(data):
            if offset + 8 > len(data):
                raise ValueError("Truncated GLB chunk header")
            size, kind = struct.unpack_from("<II", data, offset)
            offset += 8
            if offset + size > len(data):
                raise ValueError("Truncated GLB chunk")
            chunk = data[offset : offset + size]
            if kind == 0x4E4F534A:
                document = json.loads(chunk)
            elif kind == 0x004E4942:
                binary = chunk
            offset += size
        if document is None:
            raise ValueError("GLB has no JSON chunk")
    else:
        document = json.loads(data.decode("utf-8-sig"))
    buffers = []
    for buffer in document.get("buffers", []):
        uri = buffer.get("uri")
        if uri is None:
            content = binary
        elif uri.startswith("data:"):
            content = base64.b64decode(uri.split(",", 1)[1], validate=True)
        elif "://" in uri:
            raise ValueError("Remote glTF buffers are not supported")
        else:
            content = (path.parent / unquote(uri)).read_bytes()
        if content is None or len(content) < buffer["byteLength"]:
            raise ValueError("Missing or truncated glTF buffer")
        buffers.append(content)
    return document, buffers


def accessor_values(doc, buffers, index):
    acc = doc["accessors"][index]
    if "sparse" in acc:
        raise ValueError("Sparse animation accessors are not supported by validation")
    formats = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    fmt = "<" + formats[acc["componentType"]] * widths[acc["type"]]
    size = struct.calcsize(fmt)
    view = doc["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", size)
    if acc.get("byteOffset", 0) + max(0, acc["count"] - 1) * stride + size > view["byteLength"]:
        raise ValueError("Accessor exceeds its bufferView")
    return [
        struct.unpack_from(fmt, buffers[view["buffer"]], start + i * stride)
        for i in range(acc["count"])
    ]


def validate_clip(path: Path, plan: dict | None = None) -> dict:
    if plan:
        validate_plan(plan)
    doc, buffers = read_gltf(path)
    animations = [a for a in doc.get("animations", []) if a.get("name") == "SpearThrow"]
    if len(animations) != 1:
        raise ValueError("Output must contain exactly one SpearThrow animation")
    if not doc.get("skins"):
        raise ValueError("Output has no skin")
    animation = animations[0]
    affected, moving, ranges = set(), set(), []
    for channel in animation["channels"]:
        sampler = animation["samplers"][channel["sampler"]]
        times = [value[0] for value in accessor_values(doc, buffers, sampler["input"])]
        values = accessor_values(doc, buffers, sampler["output"])
        multiplier = 3 if sampler.get("interpolation") == "CUBICSPLINE" else 1
        if len(times) < 2 or len(values) != len(times) * multiplier:
            raise ValueError("Invalid animation sample count")
        if not all(math.isfinite(v) for v in times) or any(
            a >= b for a, b in zip(times, times[1:], strict=False)
        ):
            raise ValueError("Animation times must be finite and strictly increasing")
        if not all(math.isfinite(v) for row in values for v in row):
            raise ValueError("Non-finite animation transform")
        if channel["target"]["path"] == "rotation":
            if any(abs(sum(v * v for v in row) - 1) > 0.02 for row in values):
                raise ValueError("Non-unit animation quaternion")
        name = doc["nodes"][channel["target"]["node"]].get("name", "unnamed")
        affected.add(name)
        if any(
            max(abs(a - b) for a, b in zip(row, values[0], strict=False)) > 1e-4
            for row in values[1:]
        ):
            moving.add(name)
        ranges.append((min(times), max(times)))
    if not ranges:
        raise ValueError("Clip contains no channels")
    duration = max(end for _, end in ranges) - min(start for start, _ in ranges)
    if duration <= 0 or not moving:
        raise ValueError("Clip is static or has zero duration")
    if plan and abs(duration - plan["duration"]) > 1 / plan["fps"]:
        raise ValueError("Exported duration differs from the motion plan")
    return {
        "passed": True,
        "animation": "SpearThrow",
        "duration": duration,
        "channel_count": len(animation["channels"]),
        "affected_bones": sorted(affected),
        "moving_bones": sorted(moving),
        "skin_count": len(doc["skins"]),
    }
