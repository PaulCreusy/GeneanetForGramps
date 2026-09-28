# GeneanetForGramps - Custom exceptions


class GeneanetAccessError(Exception):
    """Raised when a Geneanet page could not be retrieved because access is
    blocked: an unresolved Cloudflare challenge, or a login/CAPTCHA wall
    that auto-login could not get past. This must stop the import instead
    of silently continuing to parse an empty/garbage page, which otherwise
    produces phantom nameless persons."""


class ImportCancelled(Exception):
    """Raised when the user clicks Stop on the progress dialog, to unwind
    out of the (possibly deep) recursive import instead of continuing to
    fetch and report errors for every remaining person."""
