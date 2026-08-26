---
name: agama-npm-cves-update
description: Plans and executes npm CVE fixes in the Agama web frontend (web/ folder) based on bugzilla.suse.com bugs. Guides through vulnerability analysis, MITRE CVE fetching (with rate limits), dependency overrides for nested packages, and creates grouped changelogs and commits.
version: "1.1.0"
---

# Agama NPM CVEs Update

## Overview

This skill provides a standard workflow to plan and execute fixes for npm Common Vulnerabilities and Exposures (CVEs) in the Agama web frontend based on provided `bugzilla.suse.com` bug IDs. It guides the agent through analyzing vulnerabilities bug-by-bug, fetching official CVE records, determining necessary updates (including handling spurious or already-fixed bugs), recording a plan of action, and ultimately committing the fixes.

## Helper Scripts
- `scripts/get-versions.js`: Use this script to accurately extract, deduplicate, and sort all installed versions of a dependency from `package-lock.json`. 
  - Usage: `node .gemini/skills/agama-npm-cves-update/scripts/get-versions.js <dependency_name>` (run from the `web/` directory).

## Workflow

Follow these steps when asked to investigate and fix npm CVEs for a list of Bugzilla bugs.

### Phase 1: Process the Bugs One by One (Planning)
**Do not make permanent fixes or commit changes during this phase; your goal is to plan what should be done for each bug by updating `CVE-BUG-PLAN.md`.**

#### 1. Analyze the Bug
1. Extract the CVE ID (e.g., `CVE-YYYY-NNNN`) from the bug title.
2. Extract the affected npm dependency (`$DEP`) from the bug title.

#### 2. Fetch the CVE Record
1. Fetch the official CVE record from the MITRE API using the extracted CVE ID. **Crucial: When fetching multiple records, add a `sleep 2` between curl calls to avoid rate limiting.**
   ```bash
   curl -s "https://cveawg.mitre.org/api/cve/${CVE_YYYY_NNNN}" -o "${CVE_YYYY_NNNN}.json"
   ```
2. Keep this `${CVE_YYYY_NNNN}.json` file saved for your reference during both the planning and execution phases.

#### 3. Determine the Update Path & Relevance
Navigate to the `web/` directory and investigate the dependency to determine the bug's relevance:
1. Run `node ../.gemini/skills/agama-npm-cves-update/scripts/get-versions.js <dependency_name>`.
   - **Spurious/Irrelevant:** If the dependency is "not found", the bug report may be spurious.
   - **Already Fixed/Processed:** If the dependency is present but all listed versions are already at a safe version (according to the CVE record), check project history (`git log`, `.changes` file) to see if it was already intentionally processed. If not intentionally processed, it was likely **fixed by accident** (e.g., by updating another library).
2. Determine if the dependency is `runtime` or `development` using `npm ls <dependency_name> --prod --depth=99` (if it returns a path, it's runtime, otherwise development).
3. If an update is needed, run `npm update <dependency_name>`. 
4. Check versions again with `get-versions.js`. If vulnerable legacy versions remain nested in the tree, you MUST use the `overrides` section in `package.json` to force the safe version globally (e.g., `"overrides": { "brace-expansion": "^5.0.9" }`) and run `npm install`.
5. **Revert any changes** made to `package.json` or `package-lock.json` after your investigation; this is only a planning phase.

#### 4. Document the Plan
Update the `CVE-BUG-PLAN.md` file (create it in the root directory if it doesn't exist) with your findings for this specific bug.

Include the following information in the plan for each bug:
- **Bug ID:** (e.g., bsc#123456)
- **CVE ID:** (e.g., CVE-2026-1234)
- **Dependency:** (e.g., `shell-quote`)
- **Kind:** `runtime` or `development`
- **Current Version:** The version(s) found before the update.
- **Target Version:** The safe version to update to.
- **Status:** Note if it requires a normal fix, is "Already processed", "Fixed by accident", or "Spurious".
- **Proposed Fix:** 
  - *Normal:* The specific action required (e.g., "Run `npm update shell-quote`" or "Add to overrides").
  - *Already processed:* "Skip, already processed."
  - *Fixed by accident:* "Skip update, but create .changes entry."
  - *Spurious:* "Skip entirely, dependency not in tree."

Once all bugs are analyzed, append a **Draft `.changes` entry** to the plan. It must be grouped by kind:
```changes
-------------------------------------------------------------------
TIMESTAMP_PLACEHOLDER - <your_name> <your_email>

- update runtime dependencies to:
  - dep-name 1.2.3, CVE-YYYY-NNNN (bsc#123456)
- update development dependencies to:
  - dep-name 2.3.4, CVE-YYYY-NNNN (bsc#123456)
- updated previously, listing its references for tracking:
  - dep-name 3.4.5, CVE-YYYY-NNNN (bsc#123456)
```

### Phase 2: Execute and Commit (After User Approval)
Once the `CVE-BUG-PLAN.md` is fully assembled, **stop and ask the user for approval**.

After the user approves the plan, execute the steps for each bug one by one. Handle each bug based on its identified Status:

#### 1. Initialize Changelog
Prepend the skeleton of the `.changes` entry (with the correct timestamp via `LC_ALL=C date -u +"%a %b %e %H:%M:%S UTC %Y"`) to `web/package/agama-web-ui.changes`.

#### 2. Apply the Fix & Commit (Per Bug)
For each Normal or Fixed by accident bug:
1. Apply the fix (run `npm update` or apply `overrides`). Skip this if "Fixed by accident".
2. Append the specific dependency line to the correct section (`runtime`, `development`, or `updated previously`) in the `.changes` file.
3. Extract the CVE description and wrap it to 72 characters: `jq -r '.containers.cna.descriptions[0].value' CVE-YYYY-NNNN.json | fmt -w 72`
4. Stage the modified files (`package-lock.json`, `package.json` if overrides used, and `agama-web-ui.changes`).
5. Create a git commit. The commit message must follow this exact format:
   - **Summary (first line):** `web: update <dependency> dependency (CVE-YYYY-NNNN, bsc#123456).` (or `web: <dependency> <version>, ...` for previously updated).
   - **Description:** An empty line, followed by `CVE description:`, followed by the formatted extracted text prefixed with `> `.

Repeat Phase 2 for each bug in the plan.
