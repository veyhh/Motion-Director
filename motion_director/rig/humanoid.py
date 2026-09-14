from motion_director.rig.normalize import normalize_bone

ALIASES = {
    "hips": ("hips", "pelvis"),
    "spine": ("spine", "spine0", "spine00"),
    "chest": ("chest", "upperchest", "spine2", "spine02", "spine1", "spine01"),
    "neck": ("neck", "neck1"),
    "head": ("head",),
    "shoulder": ("shoulder", "clavicle", "collar"),
    "upper_arm": ("upperarm", "arm", "uparm"),
    "lower_arm": ("lowerarm", "forearm", "loarm"),
    "hand": ("hand", "wrist"),
    "thigh": ("thigh", "upleg", "upperleg"),
    "shin": ("shin", "leg", "calf", "lowerleg"),
    "foot": ("foot", "ankle"),
    "toe": ("toe", "toebase", "toes"),
}
REQUIRED = ["hips", "spine", "head"] + [
    f"{part}.{side}"
    for side in ("l", "r")
    for part in ("upper_arm", "lower_arm", "hand", "thigh", "shin", "foot")
]


def map_humanoid(names: list[str], overrides: dict | None = None) -> dict:
    index: dict[str, list[str]] = {}
    for name in names:
        index.setdefault(normalize_bone(name), []).append(name)
    mapping, ambiguous = {}, {}
    for role, aliases in ALIASES.items():
        sides = (
            ("l", "r")
            if role
            in ("shoulder", "upper_arm", "lower_arm", "hand", "thigh", "shin", "foot", "toe")
            else (None,)
        )
        for side in sides:
            key = f"{role}.{side}" if side else role
            for alias in aliases:
                candidates = index.get(f"{alias}.{side}" if side else alias, [])
                if len(candidates) > 1:
                    ambiguous[key] = candidates
                    break
                if candidates:
                    mapping[key] = candidates[0]
                    break
    for key, value in (overrides or {}).items():
        if value not in names:
            raise ValueError(f"Bone override {key}: {value!r} does not exist")
        if key not in REQUIRED and key not in ALIASES and key.split(".")[0] not in ALIASES:
            raise ValueError(f"Unknown humanoid role: {key}")
        mapping[key] = value
        ambiguous.pop(key, None)
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("A bone cannot fulfill multiple humanoid roles")
    missing = [key for key in REQUIRED if key not in mapping]
    return {
        "mapping": mapping,
        "missing": missing,
        "ambiguous": ambiguous,
        "is_humanoid": not missing and not ambiguous,
    }
