import re


def normalize_bone(name: str) -> str:
    """Canonical name, keeping side information and discarding common namespaces."""
    name = name.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
    name = re.sub(r"^(mixamorig\d*|bip0*\d*|armature)[ _.:\-]*", "", name, flags=re.I)
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower()
    tokens = [p for p in re.split(r"[^a-z0-9]+", name) if p]
    side = None
    if tokens and tokens[0] in ("left", "right", "l", "r"):
        side = tokens.pop(0)[0]
    if tokens and tokens[-1] in ("left", "right", "l", "r"):
        side = tokens.pop()[0]
    base = "".join(tokens)
    for word, short in (("left", "l"), ("right", "r")):
        if base.startswith(word):
            base, side = base[len(word) :], short
    return f"{base}.{side}" if side else base
