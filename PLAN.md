IsoPackagesReport works by downloading large ISO files. We want to avoid that, if possible:

Have IsoPackagesReport check, by running "wwwdirfs --help", if that FUSE tool is available.
Also, run that yourself now.

Add a WWWMounter class to be used instead of downloading the ISO. It will use ?jsontable URLs.
Use $CACHE_DIR/mounts_www as base for those mounts.
Use plan mode.
