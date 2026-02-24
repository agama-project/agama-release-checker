This is written in Python, so that people and robots find it easy to read and
modify.

Specifically we target Python 3.11 or newer. On openSUSE Leap 15.6
where the default `python3` is 3.6, use `python3.11` and `pip3.11`.

Make use of ./agama-release-checker instead of calling python3 with arguments.

Read Makefile to see what checks the code should pass.
Run `make check` before committing.

In commit messages, first mention features and bugfixes, then separately
implementation details.
