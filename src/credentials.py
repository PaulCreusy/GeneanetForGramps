# GeneanetForGramps - Credential storage for Geneanet auto-login
import os
import stat
import configparser

CREDENTIALS_FILE = os.path.expanduser("~/.config/geneanetforgramps/credentials.ini")


def get_credentials():
    """Return (username, password) or (None, None) if the file is missing or incomplete."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None, None
    # interpolation=None prevents configparser from mangling passwords that contain % ( )
    cfg = configparser.RawConfigParser()
    cfg.read(CREDENTIALS_FILE)
    try:
        return cfg['geneanet']['username'], cfg['geneanet']['password']
    except KeyError:
        return None, None


def save_credentials(username, password):
    """Write credentials to CREDENTIALS_FILE with owner-only (600) permissions."""
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    cfg = configparser.RawConfigParser()
    cfg['geneanet'] = {'username': username, 'password': password}
    with open(CREDENTIALS_FILE, 'w') as f:
        cfg.write(f)
    # Restrict to owner read/write only
    os.chmod(CREDENTIALS_FILE, stat.S_IRUSR | stat.S_IWUSR)
