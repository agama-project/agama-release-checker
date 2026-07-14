# Agama Release Checker

This tool helps manage releases of [Agama][].

It tracks the progress of the code and resulting artifacts across:

1. The upstream development repo at GitHib
2. Open Build Service (OBS) both public (openSUSE) and internal (SLE) instances
3. Product ISO images at dowload.opensuse.org and download.suse.de

Taken into account are the transitional states, represented by OBS Submit
requests and Git Pull requests.

The specific projects, repos and packages are taken from a configuration file
so that this can be made useful for other teams and projects.

[Agama]: https://github.com/agama-project/agama/

### Usage

#### Release Checker

Run `./agama-release-checker --help` to see all options.

Common options:
  -c, --config FILE   Specify the configuration file (default: config.yml)
  -o, --output FILE   Specify the output file (default: agama-release-status.md)
  --timezone TZ       Specify the timezone for timestamps (default: Europe/Berlin)
  -v, --verbose       Enable verbose logging
  -r, --repo REPO     Process only the specified repository (can be repeated)

#### Release Maker

The `agama-release-maker` tool automates the submission of multiple packages
between OBS projects or from OBS/Git to Gitea repositories, including
synchronization and pull request creation.

Run `./agama-release-maker --help` to see all options and subcommands.

Common options:
  -c, --config FILE   Specify the configuration file (default: maker-config-testing.yml)
  -v, --verbose       Enable verbose logging

Subcommands:
- `obs-submit`: Submits packages between OBS projects as defined in the
  configuration file.
  Automatically creates submit requests for all configured packages using
  `osc sr --yes` for a non-interactive experience.
- `gitea-submit`: Syncs source code to Gitea and creates pull requests
  based on the configuration.
  - **Robust PR detection**: Automatically checks for existing open PRs from the
    same branch to avoid duplicate submissions.
  - **Forking support**: If a `fork_org` is specified in the configuration, the
    tool pushes to a fork instead of the target repository. This is useful when
    direct write access is restricted.
  - **Custom strategy**: For packages with a `gitea_submit` strategy in the
    configuration, it performs a custom submission from an upstream Git
    repository instead of OBS. This allows building or pre-processing source code
    (e.g., for `agama-installer`) before syncing it to a subdirectory in Gitea.

#### Requirements

The tools depend on several command-line utilities:
- `osc`: For OBS and IBS interactions.
- `git`: For repository management.
- `tea`: For Gitea pull request management.
- `fuseiso`: For Release Checker to mount ISO images.
- `filterdiff` (from `patchutils`): For Release Maker to extract `.changes` diffs.

### License

GPL-2.0-or-later (like Agama itself)

### Installation

On openSUSE Leap 16.0, install dependencies with zypper:

    zypper install python313-pytest python313-pytest-cov python313-requests-mock \
        python313-PyYAML python313-requests \
        python313-mypy python313-black

If those are not available, install uv:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Then install dependencies with:

    uv venv --python python3.11
    . .venv/bin/activate
    uv pip install '.[test]'

### Source (Annotated)

- Git repository at GitHub: <https://github.com/mvidner/agama-release-checker>
- Annotated source code: New to Python? Hover over names for documentation,
  click for reference links: <https://agama-release-checker-annotated.surge.sh/>
