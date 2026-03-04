agama-release-checker gathers enough data for now, let's work on presenting it better.

1. Add a footer: Report created with Agama Release Checker,
   linking to https://github.com/mvidner/agama-release-checker

2. Save the report to a agama-release-status.md file by default, controlled by
   an --output/-o option.

3. The timestamps in the report are too long. Add a --timezone=Europe/Berlin CLI
   option and convert all timestamps in the report to a YYYY-MM-DD HH:MM format
   in that time zone. To the "Generated on (timestamp)" note at the beginning
   of the report, add a "(all times in (timezone) time zone)".

4. Package version tables are too verbose. (If you need to see sample output,
   look at gist/agama-release-status.md)

    - Check that all Version-Release are the same for a given Source Name. If
    not, pick the first one but add a ".../!\" suffix to mean there is an
    inconsistency

    - Omit the Name column entirely, and put Version and Release on the same
      line as the Source Name

## Tasks

### Footer and Output
- [x] Add `--output/-o` option to `main.py`, default to `agama-release-status.md`
- [x] Add footer with link to the repository in `main.py`
- [x] Redirect report output to the specified file

### Timezone and Timestamps
- [x] Add `--timezone` option to `main.py`, default to `Europe/Berlin`
- [x] Implement `format_timestamp` utility in `src/agama_release_checker/utils.py`
- [x] Update "Generated on" header with timezone info
- [x] Update `print_git_report` in `src/agama_release_checker/reporting.py` to use formatted timestamps
- [x] Update `ObsRequestsReport` to use formatted timestamps
- [x] Update `GiteaRequestsReport` to use formatted timestamps
- [x] format_timestamp: change it to strictly require ISO format with time zone on input
- [x] adjust input sources to format_timestamp to be ISO with time zone. For OBS Requests
      (which have no TZ), assume UTC and add a comment: "UTC is implied, confirmed by experiment"

### Package Tables simplification
- [x] Update `IsoPackagesReport._print_packages_table`
- [x] Update `ObsPackagesReport._print_source_packages_table`
- [x] Update `GiteaPackagesReport._print_source_packages_table`

### Final Verification
- [x] Run `make check`
- [x] Manually verify formatting and timezone conversion
