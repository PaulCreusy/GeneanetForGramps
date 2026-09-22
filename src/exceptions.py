# GeneanetForGramps - Custom exceptions


class GeneanetAccessError(Exception):
    """Raised when a Geneanet page could not be retrieved because access is
    blocked: an unresolved Cloudflare challenge, or a login/CAPTCHA wall
    that auto-login could not get past. This must stop the import instead
    of silently continuing to parse an empty/garbage page, which otherwise
    produces phantom nameless persons."""
