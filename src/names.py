# GeneanetForGramps - Comparing names written by two different sources.
#
# Standalone (no Gramps imports). Geneanet and a Gramps tree often spell the
# same name with different punctuation ("Marie-Françoise" / "Marie Françoise",
# "D'Hondt" / "D’Hondt"): that is not a different person.
import unicodedata


def normalize_name(text):
    """The name with every punctuation mark or symbol read as a space, the
    spaces collapsed, the accents removed and the case folded: "Marie-Françoise"
    and "Marie Françoise" give the same result, and so do "de la Fontaine" and
    "De La Fontaine" (Geneanet capitalises every word), "Françoise" and
    "Francoise"."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    chars = [" " if unicodedata.category(c)[0] in "PS" else c
             for c in decomposed if not unicodedata.combining(c)]
    return " ".join("".join(chars).split()).casefold()


def is_unknown(firstname, lastname):
    """True for a person Geneanet shows as "? ?": every part of the name that
    is given is only question marks, and there is at least one. Nothing given
    at all is a page that could not be read, not an unknown person."""
    parts = [(part or "").strip() for part in (firstname, lastname)]
    parts = [part for part in parts if part]
    return bool(parts) and all(set(part) == {"?"} for part in parts)


def same_name(first, second):
    """True when the two names differ at most by punctuation, spacing, accents and case."""
    return normalize_name(first) == normalize_name(second)
