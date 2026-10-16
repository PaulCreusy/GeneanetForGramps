# GeneanetForGramps - Comparing names written by two different sources.
#
# Standalone (no Gramps imports). Geneanet and a Gramps tree often spell the
# same name with different punctuation ("Marie-Françoise" / "Marie Françoise",
# "D'Hondt" / "D’Hondt"): that is not a different person.
import unicodedata


def normalize_name(text):
    """The name with every punctuation mark or symbol read as a space and the
    spaces collapsed: "Marie-Françoise" and "Marie Françoise" give the same
    result. Letters, accents and case are left alone."""
    chars = [" " if unicodedata.category(c)[0] in "PS" else c for c in (text or "")]
    return " ".join("".join(chars).split())


def same_name(first, second):
    """True when the two names differ at most by punctuation and spacing."""
    return normalize_name(first) == normalize_name(second)
