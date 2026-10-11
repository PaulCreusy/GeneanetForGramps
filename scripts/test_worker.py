#!/usr/bin/python3
"""Manual smoke test for the isolated scraper worker (src/worker_env.py +
src/worker_client.py + worker/), independent of Gramps.

Usage:
    python3 scripts/test_worker.py [URL]

First run creates the dedicated worker venv under
~/.local/share/geneanetforgramps/venv (downloads Selenium there), which can
take a minute. Chrome opens visibly so a Cloudflare checkbox can be clicked
by hand if needed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from src.worker_env import ensure_worker_env, REPO_ROOT
import subprocess


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://gw.geneanet.org/cguilbert?n=guilbert&p=felix"

    python = ensure_worker_env(progress_callback=print)
    print("Starting worker:", python)
    proc = subprocess.Popen(
        [python, "-u", "-m", "worker.main", "DEBUG"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )
    try:
        proc.stdin.write(json.dumps({"cmd": "scrape", "url": url}) + "\n")
        proc.stdin.flush()
        response = json.loads(proc.stdout.readline())
        print(json.dumps(response, indent=2, ensure_ascii=False))
        input("Press Enter to close the worker...")
    finally:
        proc.stdin.write(json.dumps({"cmd": "close"}) + "\n")
        proc.stdin.flush()
        proc.wait(timeout=15)


if __name__ == "__main__":
    main()
