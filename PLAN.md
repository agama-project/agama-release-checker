agama-release-checker gathers enough data for now, let's work on presenting it better.

The Git Commits table now serves only to add timestamps. Remove the Git Commits
tables (but leave the link definitions) and add the timestamps as a Git Updated
initial column for the package tables. Sort the tables by that column.

Plan first and make a task list, adding it to this file.

## Task List
- [x] 1. Add `get_git_timestamps(git_hashes, git_configs, link_manager)` in `src/agama_release_checker/reporting.py`. It calculates a dictionary mapping `githash` to its formatted timestamp string using `GitManager.get_commit_info`.
- [x] 2. Update `print_packages_table` in `src/agama_release_checker/reporting.py`:
  - Take an optional `timestamps: dict[str, str] | None = None` argument.
  - Extract the git hash from the `version` (using regex).
  - Prepend the fetched timestamp (or "Unknown" / "") to each row.
  - Prepend "Git Updated" to the table headers.
  - Sort rows by the "Git Updated" column in descending order.
- [x] 3. Update all `*PackagesReport.render` methods to take `timestamps` and pass it to `print_packages_table`.
- [x] 4. In `src/agama_release_checker/main.py`:
  - Calculate `timestamps` using `get_git_timestamps` before the render loops.
  - Pass the `timestamps` dictionary to the `render` calls for ISO, OBS, and Gitea reports.
  - Remove `print_git_report` usage (and delete the function from `reporting.py`), keeping `link_manager.print_definitions()`.
- [x] 5. Update tests to match the new behavior and fix any broken tests.
- [x] 6. Run `pytest`, `mypy`, and `black` to verify functionality.
- [x] Instead of dict[str,str], add a dataclass for the timestamps in models.py, with a docstring. 
- [x] print_packages_table needs better examples in the docstring.
      Keep the simple one and add one with meaningful link manager and timestamps.
- [x] Refactor `dict[str, GitTimestamp]` into `GitRevisionTimestamps` dataclass.
