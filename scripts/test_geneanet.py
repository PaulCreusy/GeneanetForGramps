import socket
import subprocess
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def free_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


options = Options()
options.binary_location = "/usr/bin/chromium-browser"

profile = tempfile.mkdtemp(prefix="geneanet-chrome-")
options.add_argument("--user-data-dir=" + profile)
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
# Required on some builds (e.g. Ubuntu's snap-packaged chromium-browser):
# without an explicit port, webdriver.Chrome() below just hangs forever
# instead of raising, because the chromedriver<->Chrome handshake never
# completes. A fresh OS-assigned port avoids reusing a fixed one that could
# collide with other tools or a leftover process.
options.add_argument("--remote-debugging-port=%d" % free_tcp_port())
options.add_argument("--window-size=800,800")

driver = webdriver.Chrome(options=options)

try:
    driver.get(
        "https://gw.geneanet.org/cguilbert?n=guilbert&p=felix"
    )

    print("Title:", driver.title)
    print("URL:", driver.current_url)

    input("Press Enter when finished...")

finally:
    try:
        driver.quit()
    except Exception:
        pass
    # Belt-and-suspenders: this Chromium build doesn't always let
    # chromedriver track/kill the process it spawned, so also force-kill
    # anything still referencing our unique throwaway profile dir.
    subprocess.run(["pkill", "-9", "-f", profile], check=False)
