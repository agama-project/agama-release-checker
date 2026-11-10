import pytest
import json
import subprocess
from unittest.mock import patch, MagicMock, ANY
from agama_release_checker.maker import ReleaseMaker
from agama_release_checker.models import (
    MakerConfig,
    PackageSubmissionConfig,
    GiteaSubmitStrategy,
    ObsSubmissionsConfig,
    GiteaSubmissionsConfig,
    ObsUpdateConfig,
)


@pytest.fixture(autouse=True)
def all_tools_installed():
    """Pretends that the required commands are installed."""
    with patch("agama_release_checker.maker.shutil.which", return_value="/usr/bin/x"):
        yield


@pytest.fixture(autouse=True)
def tea_login(request):
    """Pretends that tea has an "ibs" login for every host."""
    if "real_tea_login" in request.keywords:
        yield
        return
    with (
        patch.object(ReleaseMaker, "_tea_login", return_value=["--login", "ibs"]),
        patch.object(
            ReleaseMaker,
            "_resolve_fork_org",
            side_effect=lambda configured, url: configured,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def forks_exist(request):
    """Pretends that all the forks exist."""
    if "real_fork_check" in request.keywords:
        yield
        return
    with patch.object(ReleaseMaker, "_missing_forks", return_value=[]):
        yield


@pytest.fixture
def mock_config():
    """Provides a mock MakerConfig with test packages."""
    config = MagicMock(spec=MakerConfig)
    config.package_submissions = {
        "pkg1": PackageSubmissionConfig(),
        "pkg2": PackageSubmissionConfig(),
    }
    config.obs_submissions = ObsSubmissionsConfig(
        source_project="source_proj", target_project="target_proj"
    )
    config.gitea_submissions = GiteaSubmissionsConfig(
        source_project="source_proj",
        target_org="target_org",
        target_branch="target_branch",
    )
    return config


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs(mock_run, mock_config):
    """Verifies that submit_to_obs calls osc sr with the correct arguments."""

    def run_side_effect(cmd, **kwargs):
        if "--diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "filterdiff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked changes diff", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    maker = ReleaseMaker(mock_config)
    maker.submit_to_obs([])

    # For each package (2 packages):
    # 1. osc sr --diff
    # 2. filterdiff
    # 3. osc sr
    assert mock_run.call_count == 6

    mock_run.assert_any_call(
        [
            "osc",
            "sr",
            "--yes",
            "-m",
            "Automatic update from source_proj\n\nMocked changes diff",
            "source_proj",
            "pkg1",
            "target_proj",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=None,
    )


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs_no_changes(mock_run, mock_config):
    """Verifies that submit_to_obs handles the 'no actions' error gracefully."""
    # Simulate the osc 400 error for no actions
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        ["osc", "sr"],
        output="",
        stderr="Server returned an error: HTTP Error 400: Bad Request\nThe request contains no actions. Submit requests without source changes may have skipped!",
    )

    maker = ReleaseMaker(mock_config)
    # This should NOT raise an exception
    maker.submit_to_obs(["pkg1", "pkg2"])

    assert mock_run.call_count == 4


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea performs the full sync and PR creation flow."""

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            # Return empty list to trigger PR creation
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    # Mock iterdir to avoid FileNotFoundError
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # For each package (2 packages):
    # 1. osc co (with -A)
    # 2. git clone
    # 3. git checkout -b
    # 4. iterdir + sync (mocked)
    # 5. git add
    # 6. git status
    # 7. git commit
    # 8. git push
    # 9. tea pr list
    # (PR creation adds another call if not filtered)
    assert mock_run.call_count >= 18

    mock_run.assert_any_call(
        ["osc", "-A", "https://api.suse.de", "co", "source_proj", "pkg1"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "git",
            "clone",
            "--branch",
            "target_branch",
            "gitea@src.suse.de:target_org/pkg1.git",
            ANY,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--login",
            "ibs",
            "--repo",
            "target_org/pkg1",
            "--base",
            "target_branch",
            "--head",
            "target_org:target_branch-update",
            "--title",
            "Update from OBS source_proj",
            "--description",
            "Automatic update from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_fork(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea pushes to a fork if fork_org is provided."""
    mock_config.gitea_submissions.fork_org = "fork_org"

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # Verify push to fork
    mock_run.assert_any_call(
        ["git", "push", "fork", "target_branch-update", "--force"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )

    # Verify PR creation with fork head
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--login",
            "ibs",
            "--repo",
            "target_org/pkg1",
            "--base",
            "target_branch",
            "--head",
            "fork_org:target_branch-update",
            "--title",
            "Update from OBS source_proj",
            "--description",
            "Automatic update from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_existing_pr(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea skips PR creation if one already exists."""

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "pr" in cmd and "list" in cmd:
            # Return an existing PR
            return MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "head": "target_org:target_branch-update",
                            "base": "target_branch",
                            "url": "http://example.com/pr/1",
                        }
                    ]
                ),
                stderr="",
            )
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # Verify that tea pr create was NOT called
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert not (args[0] == "tea" and args[2] == "create")

    # Verify that we avoided cloning and OBS checkout completely
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert not (args[0] == "git" and args[1] == "clone")
        assert not (args[0] == "osc")


@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_custom_existing_pr(mock_run, mock_copytree, mock_config):
    """Verifies that submit_to_gitea custom strategy avoids cloning/building if PR exists."""
    strategy = GiteaSubmitStrategy(
        source_repo="https://github.com/org/repo",
        source_run="make build",
        source_dir="dist",
        target_repo="gitea@gitea.example.com:target_owner/target_repo.git",
        target_dir="subdir",
        target_branch="custom_branch",
    )
    mock_config.package_submissions = {
        "custom-pkg": PackageSubmissionConfig(gitea_submit=strategy)
    }

    def run_side_effect(cmd, **kwargs):
        if "pr" in cmd and "list" in cmd:
            # Return an existing PR
            return MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "head": "target_owner:custom_branch-update-custom-pkg",
                            "base": "custom_branch",
                            "url": "http://example.com/pr/2",
                        }
                    ]
                ),
                stderr="",
            )
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # Verify we only did the tea pr list check, and did not clone or build
    assert mock_run.call_count == 1
    # Check that the call was indeed tea pr list
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd[0] == "tea"
    assert cmd[1] == "pr"
    assert cmd[2] == "list"


@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_custom(mock_run, mock_copytree, mock_config):
    """Verifies that submit_to_gitea uses the custom strategy when provided."""
    strategy = GiteaSubmitStrategy(
        source_repo="https://github.com/org/repo",
        source_run="make build",
        source_dir="dist",
        target_repo="gitea@gitea.example.com:target_owner/target_repo.git",
        target_dir="subdir",
        target_branch="custom_branch",
    )
    mock_config.package_submissions = {
        "custom-pkg": PackageSubmissionConfig(gitea_submit=strategy)
    }

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # 1. git clone source
    # 2. make build
    # 3. git clone target
    # 4. git checkout -b
    # 5. git add
    # 6. git status
    # 7. git commit
    # 8. git push
    # 9. tea pr list
    # 10. tea pr create
    assert mock_run.call_count >= 10

    mock_run.assert_any_call(
        ["git", "clone", "https://github.com/org/repo", ANY],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        ["make", "build"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "git",
            "clone",
            "--branch",
            "custom_branch",
            "gitea@gitea.example.com:target_owner/target_repo.git",
            ANY,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--login",
            "ibs",
            "--repo",
            "target_owner/target_repo",
            "--base",
            "custom_branch",
            "--head",
            "target_owner:custom_branch-update-custom-pkg",
            "--title",
            "Update custom-pkg from source_proj",
            "--description",
            "Automatic update of custom-pkg from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )


@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_custom_source_branch(mock_run, mock_copytree, mock_config):
    """Verifies that the custom strategy clones the configured source branch."""
    strategy = GiteaSubmitStrategy(
        source_repo="https://github.com/org/repo",
        source_run="make build",
        source_dir="dist",
        target_repo="gitea@gitea.example.com:target_owner/target_repo.git",
        target_dir="subdir",
        source_branch="SLE-16.1",
    )
    mock_config.package_submissions = {
        "custom-pkg": PackageSubmissionConfig(gitea_submit=strategy)
    }
    mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

    ReleaseMaker(mock_config).submit_to_gitea([])

    mock_run.assert_any_call(
        ["git", "clone", "--branch", "SLE-16.1", "https://github.com/org/repo", ANY],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )


@patch("agama_release_checker.maker.subprocess.run")
def test_check_builds_ok(mock_run, mock_config):
    """Verifies that check_builds checks the OBS and the IBS projects."""
    mock_config.obs_update = None
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    assert ReleaseMaker(mock_config).check_builds()

    cmds = [call.args[0] for call in mock_run.call_args_list]
    assert cmds == [
        ["osc", "results", "--failed", "source_proj"],
        ["osc", "-A", "https://api.suse.de", "results", "--failed", "source_proj"],
    ]


@patch("agama_release_checker.maker.subprocess.run")
def test_check_builds_maintenance(mock_run, mock_config):
    """Verifies that check_builds uses obs_update when there is no obs_submissions."""
    mock_config.obs_submissions = None
    mock_config.obs_update = ObsUpdateConfig(ref="SLE-16.1", project="maint_proj")
    mock_run.return_value = MagicMock(
        returncode=0, stdout="agama  SLE_16.1  x86_64  failed", stderr=""
    )

    assert not ReleaseMaker(mock_config).check_builds()
    assert mock_run.call_args_list[0].args[0] == [
        "osc",
        "results",
        "--failed",
        "maint_proj",
    ]


def test_submit_to_obs_not_configured(mock_config):
    mock_config.obs_submissions = None
    with pytest.raises(RuntimeError, match="No obs_submissions"):
        ReleaseMaker(mock_config).submit_to_obs([])


def test_maker_config_maintenance(tmp_path):
    """A maintenance configuration needs no obs_submissions."""
    path = tmp_path / "config.yml"
    path.write_text("""
package_submissions:
  agama: {}
obs_update:
  ref: SLE-16.1
  project: systemsmanagement:Agama:Maintenance:SLE-16.1
gitea_submissions:
  source_project: Devel:YaST:Agama:Maintenance:SLE-16.1
  target_org: pool
  target_branch: slfo-1.3
""")
    config = MakerConfig.from_file(path)
    assert config.obs_submissions is None
    assert config.obs_update == ObsUpdateConfig(
        ref="SLE-16.1", project="systemsmanagement:Agama:Maintenance:SLE-16.1"
    )


def test_submit_to_gitea_missing_tool(mock_config):
    with patch("agama_release_checker.maker.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="sudo zypper install .*gitea-tea"):
            ReleaseMaker(mock_config).submit_to_gitea([])


TEA_LOGINS = json.dumps(
    [
        {"name": "obs", "url": "https://src.opensuse.org", "default": "true"},
        {"name": "ibs", "url": "https://src.suse.de", "default": "false"},
    ]
)


@pytest.mark.real_tea_login
@patch("agama_release_checker.maker.subprocess.run")
def test_tea_login_matches_host(mock_run, mock_config):
    """The tea login of the target host is used, not the default one."""
    mock_run.return_value = MagicMock(returncode=0, stdout=TEA_LOGINS, stderr="")
    maker = ReleaseMaker(mock_config)

    assert maker._tea_login("src.suse.de") == ["--login", "ibs"]
    assert maker._tea_login("src.suse.de") == ["--login", "ibs"]
    assert mock_run.call_count == 1  # cached


@pytest.mark.real_tea_login
@patch("agama_release_checker.maker.subprocess.run")
def test_tea_login_missing(mock_run, mock_config):
    mock_run.return_value = MagicMock(returncode=0, stdout=TEA_LOGINS, stderr="")
    with pytest.raises(
        RuntimeError, match="tea logins add --url https://gitea.example.com"
    ):
        ReleaseMaker(mock_config)._tea_login("gitea.example.com")


@pytest.mark.real_fork_check
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_missing_fork(mock_run, mock_config):
    """Nothing is submitted if some fork is missing."""
    mock_config.gitea_submissions.fork_org = "me"

    def run(cmd, **kwargs):
        if cmd[:2] == ["tea", "api"]:
            if cmd[-1] == "/repos/me/pkg1":
                out = {"fork": True, "parent": {"full_name": "target_org/pkg1"}}
            else:
                out = {"message": "not found"}
            return MagicMock(returncode=0, stdout=json.dumps(out), stderr="")
        return MagicMock(returncode=0, stdout="[]", stderr="")

    mock_run.side_effect = run

    with pytest.raises(
        RuntimeError, match=r"no fork of: https://src.suse.de/target_org/pkg2\."
    ):
        ReleaseMaker(mock_config).submit_to_gitea([])
    assert not any(c.args[0][:2] == ["git", "clone"] for c in mock_run.call_args_list)


@pytest.mark.real_tea_login
@patch("agama_release_checker.maker.subprocess.run")
def test_fork_org_from_tea_login(mock_run, mock_config):
    """Without a configured fork_org, the user of the tea login is used."""
    logins = [{"name": "ibs", "url": "https://src.suse.de", "user": "teclator"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(logins))
    maker = ReleaseMaker(mock_config)

    assert (
        maker._resolve_fork_org(None, "gitea@src.suse.de:pool/agama.git") == "teclator"
    )
    assert maker._resolve_fork_org("me", "gitea@src.suse.de:pool/agama.git") == "me"


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs_summary(mock_run, mock_config, capsys):
    def run(cmd, **kwargs):
        if cmd[:3] == ["osc", "sr", "--yes"] and cmd[-2] == "pkg2":
            raise subprocess.CalledProcessError(
                1, cmd, stderr="The request contains no actions"
            )
        if cmd[:3] == ["osc", "sr", "--yes"]:
            return MagicMock(returncode=0, stdout="created request id 1234\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = run
    maker = ReleaseMaker(mock_config)
    maker.submit_to_obs([])
    maker.print_summary()

    assert maker.results == [
        ("pkg1", "submitted", "request 1234"),
        ("pkg2", "no changes", ""),
    ]
    assert "pkg1  submitted      request 1234" in capsys.readouterr().out


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_summary_failure(mock_run, mock_config):
    """A failed package is recorded before the error is propagated."""
    mock_run.side_effect = subprocess.CalledProcessError(1, ["tea"], stderr="boom")

    maker = ReleaseMaker(mock_config)
    with pytest.raises(subprocess.CalledProcessError):
        maker.submit_to_gitea([])
    assert maker.results[-1][:2] == ("pkg1", "failed")


def test_main_error_is_short(tmp_path, capsys, caplog):
    """main() reports errors in one line instead of a traceback."""
    from agama_release_checker import maker as maker_module

    config = tmp_path / "c.yml"
    config.write_text(
        "package_submissions: {agama: {}}\n"
        "gitea_submissions: {source_project: p, target_org: o, target_branch: b}\n"
    )
    with patch("sys.argv", ["maker", "-c", str(config), "obs-submit"]):
        with pytest.raises(SystemExit) as exit_info:
            maker_module.main()
    assert exit_info.value.code == 1
    assert "Stopped: No obs_submissions in the configuration" in caplog.text
