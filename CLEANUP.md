Now that the initial functionality is in place, it is time to take a pause and
revise the project design, make sure it is sound.

We are still constrained mainly by the external systems providing the data.
But we may have been sloppy in naming the concepts used, organizing the config and the code.


## Core concepts summary

It all boils down to a bunch of **packages** that have

1. type (git source, OBS source, RPM)
2. name
3. version (numbered, named, hash)

These packages are grouped in **repositories** of several kinds: OBS, Gitea, ISO.

Packages progress from one repo to another by one of these steps:

1. **build** (may fail) - the tool is not tracking this yet
2. submission **requests** (Git Pull Request, OBS Submit Request; may be declined)


## Core concepts in detail

### Package: Upstream Source Repository

This is the usual Git repository. It may be hosted on GitHub but that is not
important now.

Do not confuse with a Gitea distro package source.

### Package: Distro Package Source: OBS

(Open Build Service, formerly openSUSE Build Service, is of course concerned
with *building* the packages but historically it has had a version control
component for managing the source packages.)

Tools: `osc`

### Package: Distro Package Source: Gitea

Also Git, but taking over the version control aspect of OBS: contains spec files
and large binary tarballs.

Tools: `tea`

### Package: Source RPM

These mostly correspond 1:1 to Distro source packages, except in cases where one
Distro source has multiple Source RPMs (via a _multibuild file).

### Package: Binary RPM

One Source RPM produces one or more Binary RPMs. Mostly one of them is named the
same as the source, but there are important exceptions.

### Repository: OBS

### Repository: Gitea

What would be different projects in OBS may be same project with different
branches here.

### Repository: ISO

An ISO-9660 CD/DVD image that is an installation medium and contains binary RPMs

### Repository: Mirrorcache

For our purposes this is a HTML page with a directory of built files and we are
interested in ISOs.

### Transition: Git Pull Request

### Transition: OBS Submit Request
