# GeneanetForGramps - isolated scraper worker package
#
# Everything under this package runs inside its own dedicated venv (see
# src/worker_env.py), NOT inside Gramps' Python process. It must stay
# importable with only the packages listed in requirements-worker.txt
# installed - no `import gramps...` anywhere in this package.
