---
name: agama-npm-cves-update
description: Plans and executes npm CVE fixes in the Agama web frontend (web/ folder) based on bugzilla.suse.com bugs. Use this skill to investigate bugzilla bugs, fetch CVE data from MITRE, generate a CVE-BUG-PLAN.md, and then execute and commit the fixes.
---

# Agama NPM CVEs Update

## Overview

This skill provides a standard workflow to plan and execute fixes for npm Common Vulnerabilities and Exposures (CVEs) in the Agama web frontend based on provided `bugzilla.suse.com` bug IDs. It guides the agent through analyzing vulnerabilities bug-by-bug, fetching official CVE records, determining necessary updates (including handling spurious or already-fixed bugs), recording a plan of action, and ultimately committing the fixes.

## Workflow

Follow these steps when asked to investigate and fix npm CVEs for a list of Bugzilla bugs.

### Phase 1: Process the Bugs One by One (Planning)
**Do not make permanent fixes or commit changes during this phase; your goal is to plan what should be done for each bug by updating `CVE-BUG-PLAN.md`.**

#### 1. Analyze the Bug
1. Extract the CVE ID (e.g., `CVE-YYYY-NNNN`) from the bug title.
2. Extract the affected npm dependency (`$DEP`) from the bug title.

#### 2. Fetch the CVE Record
1. Fetch the official CVE record from the MITRE API using the extracted CVE ID:
   ```bash
   curl -s "https://cveawg.mitre.org/api/cve/${CVE_YYYY_NNNN}" -o "${CVE_YYYY_NNNN}.json"
   ```
2. Keep this `${CVE_YYYY_NNNN}.json` file saved for your reference during both the planning and execution phases.

#### 3. Determine the Update Path & Relevance
Navigate to the `web/` directory and investigate the dependency to determine the bug's relevance:
1. Run `npm list <dependency_name>` (e.g., `npm list $DEP`).
   - **Spurious/Irrelevant:** If the dependency is not in the tree at all, the bug report may be spurious.
   - **Already Fixed/Processed:** If the dependency is present but already at a safe version, check project history (`git log`, `.changes` file) to see if it was already intentionally processed. If not intentionally processed, it was likely **fixed by accident** (e.g., by updating another library).
2. If an update is needed, run `npm update <dependency_name>` to see if a simple update resolves the vulnerability based on current version constraints.
3. If `npm update` does not resolve the issue, try manually updating the relevant version requirement in `package.json` to see what changes are necessary.
4. **Revert any changes** made to `package.json` or `package-lock.json` after your investigation; this is only a planning phase.

#### 4. Document the Plan
Update the `CVE-BUG-PLAN.md` file (create it in the root directory if it doesn't exist) with your findings for this specific bug.

Include the following information in the plan for each bug:
- **Bug ID:** (e.g., bsc#123456)
- **CVE ID:** (e.g., CVE-2026-1234)
- **Dependency:** (e.g., `shell-quote`)
- **Status:** Note if it requires a normal fix, is "Already processed", "Fixed by accident", or "Spurious".
- **Proposed Fix:** 
  - *Normal:* The specific action required (e.g., "Run `npm update shell-quote`").
  - *Already processed:* "Skip, already processed."
  - *Fixed by accident:* "Skip update, but create .changes entry."
  - *Spurious:* "Skip entirely, dependency not in tree."
- **.changes Entry Draft:** A draft of the entry that will eventually be added to `web/package/agama-web-ui.changes` (Not needed for Spurious or Already processed bugs). Format example:
  `- Update <dependency_name> dependency (CVE-YYYY-NNNN, bsc#<bug_number>).`

Repeat this process for every bug provided in the request.

### Phase 2: Execute and Commit (After User Approval)
Once the `CVE-BUG-PLAN.md` is fully assembled, **stop and ask the user for approval**.

After the user approves the plan, execute the steps for each bug one by one. Handle each bug based on its identified Status:

#### 1. Apply the Fix
- **Spurious or Already Processed:** Skip this bug entirely.
- **Fixed by accident:** Skip the `npm` update commands, but proceed to step 2 to create the `.changes` entry.
- **Normal:** Navigate to the `web/` directory and run the planned `npm update` or `npm install` command as defined in the approved plan.

#### 2. Update the .changes file
*(Only for Normal and Fixed by accident bugs)*
1. Add the drafted `.changes` entry to the top of `web/package/agama-web-ui.changes`.
2. Run `date -u +"%a %b %e %H:%M:%S UTC %Y"` to get the correct timestamp format for the block.

#### 3. Extract CVE Description
*(Only for Normal and Fixed by accident bugs)*
Read the downloaded `${CVE_YYYY_NNNN}.json` file to extract the English CVE description. You can use `jq` to parse the JSON (e.g., identifying the English description under the `containers.cna.descriptions` array for CVE JSON v5).

#### 4. Commit the Changes
*(Only for Normal and Fixed by accident bugs)*
1. Stage the modified files: `git add web/package-lock.json web/package/agama-web-ui.changes` (and `web/package.json` if modified). For "Fixed by accident", you will only be staging the `.changes` file.
2. Create a git commit for this specific bug. The commit message must follow this exact format:
   - **Summary (first line):** `web: ` followed by the `.changes` entry text (removing the leading dash and space).
   - **Description:** An empty line, followed by `CVE description:`, followed by the extracted text prefixed with `> `.

**Example Commit Message:**
```text
web: Update shell-quote dependency (CVE-2026-1234, bsc#123456).

CVE description:
> The shell-quote package before 1.9.0 is vulnerable to arbitrary command injection...
```

Repeat Phase 2 for each bug in the plan.
