---
trigger: always_on
---

# Environment Configuration
When executing Python commands, ALWAYS use the interpreter located at:
`./.venv/bin/python` (or `.\.venv\Scripts\python.exe` on Windows).
You need to activate the virtual environment first by using the activation script (`./.venv/bin/activate` or `.\.venv\Scripts\Activate.ps1`).

Do not run `python` directly from the global path.

There are also some predefined commands in Makefile, prioritize them before using custom ones.