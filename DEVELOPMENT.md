# The 4 core principles


**1. Separate Code from Runtime**  
- No side effects (DB connections, browser launches, file writes) at module level.  
- Put all heavy initialization inside explicitly called methods/functions.  
- Use `if __name__ == "__main__"` to isolate execution.

**2. Use Shared Utilities – No Hard‑coding**  
- Configuration: always use `get_config()` (YAML + .env) – never hard‑code paths, credentials, or URLs.  
- Logging: use a project‑wide logger; never `print()`.

**3. Manage Resources and Errors Properly**  
- Use context managers (`with`) for files, connections, drivers.  
- Catch specific exceptions, log with full context, and implement retries for unstable operations (network, DB).

**4. Test, CI, and Dependencies**  
- Write unit tests (with mocks) and integration tests (with containers).  
- Run all tests automatically on every PR/push to main via CI.  
- Maintain a `requirements.txt` with pinned versions.
