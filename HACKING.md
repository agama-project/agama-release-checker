This is written in Python, so that people and robots find it easy to read and
modify.

Specifically we target Python 3.11 or newer. On openSUSE Leap 15.6
where the default `python3` is 3.6, use `python3.11` and `pip3.11`.

Install dependencies with zypper if available, otherwise with uv:

    zypper install python311-pytest python311-pytest-cov python311-requests-mock \
        python311-PyYAML python311-requests python311-beautifulsoup4 \
        python311-mypy python311-black

If zypper is not available, install uv:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Then install dependencies with:

    uv pip install --python python3.11 '.[test]'

Make use of ./agama-release-checker instead of calling python3 with arguments.

Read Makefile to see what checks the code should pass.
Run `make check` before committing.

In commit messages, first mention features and bugfixes, then separately
implementation details.
