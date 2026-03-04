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
