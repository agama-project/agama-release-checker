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

Run `./agama-release-maker --help` to see all options and subcommands.

Subcommands:
- `obs-submit SOURCE TARGET`: Submits packages from SOURCE OBS project to TARGET project.
- `gitea-submit SOURCE ORG BRANCH`: Syncs OBS SOURCE project to Gitea ORG on BRANCH and creates pull requests.

### License

GPL-2.0-or-later (like Agama itself)

### Installation

Install dependencies with zypper if available:

    zypper install python311-pytest python311-pytest-cov python311-requests-mock \
        python311-PyYAML python311-requests \
        python311-mypy python311-black

If zypper is not available, install uv:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Then install dependencies with:

    uv pip install --python python3.11 '.[test]'

### Source (Annotated)

- Git repository at GitHub: <https://github.com/mvidner/agama-release-checker>
- Annotated source code: New to Python? Hover over names for documentation,
  click for reference links: <https://agama-release-checker-annotated.surge.sh/>
