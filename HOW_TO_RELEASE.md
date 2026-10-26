# How to Release a New Version of Agama

This document explains how to release a new version of Agama from the `master`
branch and submit it to openSUSE Factory and to the next SLE release. It is
meant to be enough for any teammate to do a submission on their own.

Updates for already released SLE versions (e.g., SLE 16.0 or 16.1) follow a
different flow, described in [Maintenance Updates for SLE](#maintenance-updates-for-sle).

## Big Picture

### Packages

Agama delivers 5 packages to OBS from [its sources](https://github.com/agama-project/agama):

| Package              | Sources (in the agama repo) | Type | Submitted to                  |
|----------------------|-----------------------------|------|-------------------------------|
| `agama`              | `rust/`                     | RPM  | Factory, SLE (`pool/agama`)   |
| `agama-web-ui`       | `web/`                      | RPM  | Factory, SLE (`pool/agama-web-ui`) |
| `rubygem-agama-yast` | `service/`                  | RPM  | Factory, SLE (`pool/rubygem-agama-yast`) |
| `agama-products`     | `products.d/`               | RPM  | Factory, SLE (`pool/agama-products`) |
| `agama-installer`    | `live/`                     | ISO  | Factory, SLE (`products/SLES`) |

Note that `agama-installer` is not an RPM that goes to the SLE `pool`
repositories: its sources are generated and submitted to the `products/SLES`
repository.

The version of the packages is based on the latest GitHub tag (e.g., `v24`),
the commit offset since the tag and the last commit hash (e.g.,
`24+95.c7bc9ea9e`).

### Projects and Repositories

* [systemsmanagement:Agama:Devel](https://build.opensuse.org/project/show/systemsmanagement:Agama:Devel) (OBS)
  * Contains the latest sources (`master` branch).
  * The GitHub workflows commit a new package revision after merging into
    `master`. A revision is created only if the sources of the package change.
    For example, if `rust/` changes, then only `agama` is committed. See for
    example [obs-staging-rust.yml](https://github.com/agama-project/agama/blob/master/.github/workflows/obs-staging-rust.yml).
* [systemsmanagement:Agama:Release](https://build.opensuse.org/project/show/systemsmanagement:Agama:Release) (OBS)
  * Contains the latest sources released to Factory.
  * The Factory submit requests are created from this project.
* [Devel:YaST:Agama:Release](https://build.suse.de/project/show/Devel:YaST:Agama:Release) (IBS)
  * Links to *systemsmanagement:Agama:Release*.
  * The sources submitted to SLE are taken from here.
* [pool/&lt;package&gt;](https://src.suse.de/pool) (Gitea at src.suse.de)
  * SLE sources of each RPM package live in Git. The branch `slfo-main` is used
    for the next SLE release.
* [products/SLES](https://src.suse.de/products/SLES) (Gitea at src.suse.de)
  * Contains the sources of the ISO (directory `agama-installer-SLES`).

~~~text
 GitHub agama (master)
        |
        | GitHub workflows (on every merge)
        v
  OBS Devel
  (systemsmanagement:Agama:Devel)

        |  tag vNN + branch2obs.sh
        v
  OBS Release  ----------- osc sr ---------->  openSUSE:Factory
  (systemsmanagement:Agama:Release)
        |
        | linked
        v
  IBS Release  --- copy sources + PR --->  src.suse.de  pool/<package>  (slfo-main)
  (Devel:YaST:Agama:Release)

  GitHub agama live/ --- make sles + PR -->  src.suse.de  products/SLES
~~~

### Phases

1. [Prepare the release](#1-prepare-the-release): changelogs, version bump and PR.
2. [Tag and publish](#2-tag-the-version) the version to the *Release* project.
3. [Submit to Factory](#5-submit-to-factory).
4. [Submit to SLE](#6-submit-the-rpm-packages-to-sle): RPM packages and ISO sources.

## Prerequisites

You only need to do this once:

* Write access to the [agama repository](https://github.com/agama-project/agama)
  and a GPG key to sign tags.
* `osc` configured for both OBS and IBS.
* The [gh](https://cli.github.com/) command line tool.
* An account at [src.suse.de](https://src.suse.de) with your SSH key, and a fork
  of each of these repositories:
  * [pool/agama](https://src.suse.de/pool/agama)
  * [pool/agama-web-ui](https://src.suse.de/pool/agama-web-ui)
  * [pool/rubygem-agama-yast](https://src.suse.de/pool/rubygem-agama-yast)
  * [pool/agama-products](https://src.suse.de/pool/agama-products)
  * [products/SLES](https://src.suse.de/products/SLES)

  If you already have the forks, make sure that they are up-to-date.
* A checkout of the agama repository.

In the following sections, we use `v25` as the example version and `USERNAME`
for your user name at src.suse.de.

## Manual Process

### 1. Prepare the Release

Create a new branch for the release:

~~~bash
git switch master
git pull
git checkout -b release-25
~~~

Update the changelog of each one of the 5 packages.

Bump the version at *service/Gemfile.lock* and *live/src/agama-installer.kiwi*.

Create a pull request. Add to the description the list of pull requests included
in this new release. You can get the list with (adapt the dates to the period
since the previous release):

~~~bash
gh search prs --repo agama-project/agama --merged-at "FROM_DATE..TO_DATE" --base master \
  --limit 200 \
  --json number \
  --template '{{range .}}* #{{.number}}{{"\n"}}{{end}}'
~~~

See [this example](https://github.com/agama-project/agama/pull/4118) if you have
any doubt. Wait until the CI is done and the pull request is merged.

### 2. Tag the Version

Once the PR is merged, tag the new version:

~~~bash
git switch master
git pull
git tag -s v25 -m "Version 25"
git push --tags
~~~

### 3. Update the Release Project

Commit the packages to the *release* project (*systemsmanagement:Agama:Release*)
using the `branch2obs.sh` script. It lives in the `devel/` directory of the
agama repository:

~~~bash
cd devel
./branch2obs.sh -p systemsmanagement:Agama:Release
~~~

The previous call changes the target project of `master`, so set it back to
*devel* again:

~~~bash
./branch2obs.sh -p systemsmanagement:Agama:Devel
~~~

### 4. Check the Builds

Check that all packages build in the *Release* projects (the IBS project is
linked to the OBS one, so it may take a while to be updated). No output means no
failures:

~~~bash
osc results --failed systemsmanagement:Agama:Release
osc --api https://api.suse.de results --failed Devel:YaST:Agama:Release
~~~

### 5. Submit to Factory

Create a submit request to Factory for every package, including
`agama-installer`:

~~~bash
for package in agama agama-installer agama-products agama-web-ui rubygem-agama-yast; do
  osc sr systemsmanagement:Agama:Release $package openSUSE:Factory
done
~~~

### 6. Submit the RPM Packages to SLE

SLE sources live in Git. For each one of the 4 RPM packages (`agama`,
`rubygem-agama-yast`, `agama-web-ui` and `agama-products`) you should:

1. Make sure that your fork of `pool/$PACKAGE` is up-to-date.
2. Get the updated sources from the IBS project
   [Devel:YaST:Agama:Release](https://build.suse.de/project/show/Devel:YaST:Agama:Release).
3. Copy the updated sources to your fork and create a PR against the
   `slfo-main` branch of the `pool/$PACKAGE` repository.

Example for the `agama` package:

~~~bash
osc --api https://api.suse.de co Devel:YaST:Agama:Release agama
git clone gitea@src.suse.de:USERNAME/agama.git
cd agama
git checkout slfo-main
git checkout -b slfo-main-update
cd ..
cp Devel\:YaST\:Agama\:Release/agama/* agama/
cd agama
git add .
git commit -m "Update from OBS Devel:YaST:Agama:Release"
git push -u origin slfo-main-update
~~~

Now create a PR against `pool/agama` branch `slfo-main`. See [this
example](https://src.suse.de/pool/agama/pulls/52) if you have any doubt.

### 7. Submit the ISO Sources to SLE

The `agama-installer` sources live in Git at
[products/SLES](https://src.suse.de/products/SLES), directory
`agama-installer-SLES`.

First, in an agama checkout, generate the sources:

~~~bash
cd live
make clean; make sles
~~~

You can find the result in the `dist` directory. Now, clone your fork of
`products/SLES`, copy the content of `dist` to the `agama-installer-SLES`
directory, and push it to a new branch:

~~~bash
git clone gitea@src.suse.de:USERNAME/SLES.git
cd SLES
git checkout -b agama-installer-update
cp -r ../agama/live/dist/* agama-installer-SLES/
git add .
git commit -m "Update agama-installer from Devel:YaST:Agama:Release"
git push -u origin agama-installer-update
~~~

Now create a PR against `products/SLES`, using the branch that corresponds to
the next SLE release. See [this example](https://src.suse.de/products/SLES/pulls/965)
if you have any doubt.

## Automatic Submission

Steps 5, 6 and 7 (Factory, SLE packages and ISO sources) can be done
automatically with the
[agama-release-maker](README.md#release-maker) script. Steps 1 to 4 are still
manual: the script expects the *Release* projects to be up-to-date.

### Setup

You only need to do this once.

* Clone the *agama-release-checker* repository:

  ~~~bash
  git clone git@github.com:agama-project/agama-release-checker.git
  ~~~

* Install the dependencies of the script:

  ~~~bash
  sudo zypper install python313-pytest python313-pytest-cov python313-requests-mock \
      python313-PyYAML python313-requests \
      python313-mypy python313-black \
      osc git gitea-tea patchutils
  ~~~

* Have your forks of the Gitea repositories (see [Prerequisites](#prerequisites)).

* Configure the Gitea login:

  ~~~bash
  tea logins add --url https://src.suse.de --name IBS --user USERNAME --oauth
  ~~~

### Configuration

Prepare a configuration file, e.g., a copy of *maker-config-production.yml*:

~~~yaml
package_submissions:
  # these 4 produce RPMs
  agama: {}
  agama-products: {}
  agama-web-ui: {}
  rubygem-agama-yast: {}
  # also from the agama repo, but it produces an ISO
  agama-installer:
    gitea_submit:
      source_repo: "https://github.com/agama-project/agama/"
      source_run: "make -C live clean sles"
      source_dir: "live/dist"
      target_repo: "gitea@src.suse.de:products/SLES.git"
      target_dir: "agama-installer-SLES"
      # Adapt the branch corresponding to the next release
      target_branch: "16.2"

obs_submissions:
  source_project: "systemsmanagement:Agama:Release"
  target_project: "openSUSE:Factory"

gitea_submissions:
  source_project: "Devel:YaST:Agama:Release"
  # your username in Gitea
  fork_org: USERNAME
  target_org: pool
  target_branch: slfo-main
~~~

* `package_submissions` lists the packages to submit. An empty value means a
  regular RPM package. `agama-installer` has a `gitea_submit` section describing
  how to build the ISO sources from the agama repository and which directory and
  branch of `products/SLES` receives them.
* `obs_submissions` defines the OBS submission to Factory (step 5).
* `gitea_submissions` defines the submission of the RPM packages to the `pool`
  repositories (step 6).

What you have to adapt for each release: `fork_org` (your user name) and the
`target_branch` of `agama-installer` (the branch of `products/SLES` of the next
SLE release).

### Running the Script

Submit everything:

~~~bash
./agama-release-maker -c maker-config-production.yml
~~~

The script allows submitting to Factory and to Gitea separately. You can submit
to Factory first, and if everything is OK, then to Gitea:

~~~bash
./agama-release-maker -c maker-config-production.yml obs-submit
./agama-release-maker -c maker-config-production.yml gitea-submit
~~~

Use `-v` for verbose output. The script creates the submit requests and the pull
requests for every package. If an open PR from the same branch already exists, it
does not create a duplicate.

### After Running the Script

Check that the pull requests were created in src.suse.de, and follow the review
until they are accepted.

## Maintenance Updates for SLE

SLES products are updated with the so-called Quarterly Updates. The changes for
a Quarterly Update are sent to a specific branch of the `pool/<package>`
repositories at src.suse.de, one per SLE version. The sources come from a
maintenance branch of the agama repository, not from `master`.

### Maintenance Streams

| SLE  | agama branch | OBS project                                    | IBS project                             | pool branch | products/SLES branch |
|------|--------------|------------------------------------------------|-----------------------------------------|-------------|----------------------|
| 16.0 | `SLE-16`     | `systemsmanagement:Agama:Maintenance:SLE-16.0` | `Devel:YaST:Agama:Maintenance:SLE-16`   | `slfo-1.2`  | `16.0`               |
| 16.1 | `SLE-16.1`   | `systemsmanagement:Agama:Maintenance:SLE-16.1` | `Devel:YaST:Agama:Maintenance:SLE-16.1` | `slfo-1.3`  | `16.1`               |

Note that for 16.0 the IBS project is named `SLE-16`, while the OBS project is
named `SLE-16.0`.

Each IBS project links to the OBS project of the same stream. Each agama branch
is always associated with its OBS project.

The differences with a regular release are:

* There is no submission to Factory.
* There is no tag and no release pull request.
* The sources come from the maintenance branch of the agama repository.

~~~text
 GitHub agama (branch SLE-16.1)
        |
        | branch2obs.sh
        v
  OBS Maintenance
  (systemsmanagement:Agama:Maintenance:SLE-16.1)
        |
        | linked
        v
  IBS Maintenance  --- copy sources + PR --->  src.suse.de  pool/<package>  (slfo-1.3)
  (Devel:YaST:Agama:Maintenance:SLE-16.1)

  GitHub agama (branch SLE-16.1) --- make sles + PR -->  src.suse.de  products/SLES (16.1)
~~~

The following steps use SLE 16.1 as the example. For another stream, use the
values from the table above. The [prerequisites](#prerequisites) are the same as
for a regular release.

### 1. Commit a New Revision to OBS

Commit the packages to the OBS maintenance project of the stream using the
`branch2obs.sh` script, from the maintenance branch:

~~~bash
git switch SLE-16.1
git pull
cd devel
./branch2obs.sh -p systemsmanagement:Agama:Maintenance:SLE-16.1
~~~

Unlike in a regular release, you do not have to set the target project back
afterwards.

Check that the packages build in the OBS project and in the linked IBS project
(the IBS project may take a while to be updated). No output means no failures:

~~~bash
osc results --failed systemsmanagement:Agama:Maintenance:SLE-16.1
iosc results --failed Devel:YaST:Agama:Maintenance:SLE-16.1
~~~

### 2. Submit the RPM Packages to SLE

Once the IBS project is updated, send the changes of the 4 RPM packages to the
`pool` repositories with the [agama-release-maker](README.md#release-maker)
script. The setup is the same as in [Automatic Submission](#setup).

Prepare a configuration file for the stream (e.g., *maker-config-sle-161.yml*):

~~~yaml
package_submissions:
  agama: {}
  agama-products: {}
  agama-web-ui: {}
  rubygem-agama-yast: {}

# there is no submission to OBS in maintenance, but the section is required
obs_submissions:
  source_project: "nosuchproject"
  target_project: "nosuchproject"

gitea_submissions:
  source_project: "Devel:YaST:Agama:Maintenance:SLE-16.1"
  # your username in Gitea
  fork_org: USERNAME
  target_org: pool
  target_branch: slfo-1.3
~~~

For another stream, change `source_project` and `target_branch` according to the
table above.

Send the changes:

~~~bash
./agama-release-maker -c maker-config-sle-161.yml gitea-submit
~~~

The script creates a pull request for every package. If you prefer to do it by
hand, follow the [step 6](#6-submit-the-rpm-packages-to-sle) of the regular
release, using the IBS project and the `pool` branch of the stream.

### 3. Submit the ISO Sources to SLE

The `agama-installer` sources have to be submitted manually. Follow the
[step 7](#7-submit-the-iso-sources-to-sle) of the regular release with these
differences:

* Switch the agama checkout to the maintenance branch (e.g., `git switch
  SLE-16.1`) before running `make clean sles`.
* Create the PR against the branch of `products/SLES` of the stream (e.g.,
  `16.1`).

> **Note:** *agama-release-maker* is able to submit the ISO sources
> (`gitea_submit` of `agama-installer`), but it does not support the
> `source_branch` option yet, which is needed to build from a maintenance
> branch.

### 4. Check the Result

Check that the pull requests were created in src.suse.de, one for each of the
4 RPM packages and one for the ISO sources, and follow the review until they are
accepted.
