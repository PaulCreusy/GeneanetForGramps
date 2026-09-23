from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.chrome.service import Service as ChromeService
import tempfile

options = Options()
options.binary_location = "/usr/bin/chromium-browser"

profile = tempfile.mkdtemp(prefix="geneanet-chrome-")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--remote-debugging-port=9222")
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
    driver.quit()
