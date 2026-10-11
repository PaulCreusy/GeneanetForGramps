# GeneanetForGramps - Scraper worker entry point.
#
# Run inside the dedicated worker venv (see src/worker_env.py), never inside
# Gramps' own Python process. Speaks a trivial line-delimited JSON protocol
# over stdin/stdout with the WorkerClient running in Gramps: one JSON
# request per line in, one JSON response per line out. All logging goes to
# stderr so it never corrupts the stdout protocol stream.
import json
import logging
import sys

from src.exceptions import GeneanetAccessError

LOG = logging.getLogger("GeneanetForGramps.worker")


def _configure_logging():
    level_name = sys.argv[1] if len(sys.argv) > 1 else "WARNING"
    level = getattr(logging, level_name, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[worker] %(message)s"))
    LOG.setLevel(level)
    LOG.addHandler(handler)


def main():
    _configure_logging()
    # Imported after logging is configured, and only once we are about to
    # actually need it - keeps worker startup fast for the "close" case.
    from worker import scraper

    LOG.info("Worker ready.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            LOG.error("Received malformed request: %r", line)
            continue

        cmd = request.get("cmd")
        if cmd == "close":
            scraper.close_driver()
            print(json.dumps({"ok": True}), flush=True)
            break
        elif cmd == "scrape":
            try:
                data = scraper.scrape_person(request["url"])
                print(json.dumps({"ok": True, "data": data}), flush=True)
            except GeneanetAccessError as e:
                print(json.dumps({"ok": False, "error_type": "access", "error": str(e)}), flush=True)
            except Exception as e:
                LOG.error("Scraping failed", exc_info=True)
                print(json.dumps({"ok": False, "error_type": "generic", "error": str(e)}), flush=True)
        else:
            print(json.dumps({"ok": False, "error_type": "generic", "error": "Unknown command: %r" % cmd}), flush=True)

    scraper.close_driver()
    LOG.info("Worker exiting.")


if __name__ == "__main__":
    main()
