agama-release-checker gathers enough data for now, let's work on presenting it better.

The Git Commits section of the report is too paper oriented.
Let's integrate it to links in the package reports:

Run diff -u agama-release-status.md.1 agama-release-status.md
to get an idea how to do it, then append a plan with tasks to this file.

### Tasks
- [x] Create a `LinkManager` in `reporting.py` to collect and manage git commit reference links.
- [x] Update `extract_git_hashes` or create a new function to associate hashes with their repository configurations.
- [x] Modify `print_packages_table` to accept an optional `LinkManager` and use it to format versions with reference links.
- [x] Update `print_git_report` to:
    - Register found hashes in `LinkManager`.
    - Use reference-style links in its own table.
    - Omit the explicit "Link" column if redundant, or leave it empty as seen in the diff.
- [x] Ensure all report `render` methods pass the `LinkManager` to `print_packages_table`.
- [x] Print all reference link definitions at the very end of the report.
- [x] Ensure docstrings are present, with examples.
- [x] Ensure unit tests are added.
