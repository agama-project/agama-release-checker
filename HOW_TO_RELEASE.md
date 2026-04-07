## Preparing the next release

You should follow these steps:

1. Create a PR to upgrade the versions. See [https://github.com/agama-project/agama/pull/2405](https://github.com/agama-project/agama/pull/2405 "smartCard-inline"). Please, wait until all the CI is done before continuing.
2. Then you can tag the version to be released: `git tag -s v16 -m "Version 16"`. Push the tag (`git push --tags`).
3. Wait until the CI ran. Please, check that the sources in OBS are up-to-date.
4. Now branch the project: `git checkout -b rc2` and `git push origin rc2`.
5. From that branch, use the `branch2obs.sh` script to update the release project (`branch2obs.sh -p systemsmanagement:Agama:Release`).

Once everything is settled, proceed with the submission process.

## Submission process

Once all CI tasks are done, you must submit the project to openSUSE and SLE.

### Submit to Factory (openSUSE)

Create submissions to factory (to avoid problems during the review). Include the `agama-installer` package too.

```
osc sr systemsmanagement:Agama:Release <package name> openSUSE:Factory
```

### Submit to SUSE:SLFO:Main (SLE)

Create submissions to SUSE:SLFO:Main for all packages except `agama-installer`. The command is (isc is shortcut to osc with internal API):

```shell
isc sr Devel:YaST:Agama:Release <package name> SUSE:SLFO:Main
```

### Submit ISO sources (SLE)

`agama-installer` sources live in Git. You can find them [here](https://src.suse.de/products/SLES/src/branch/16.0/agama-installer-SLES "‌baf"). First, in an `agama` checkout, you need to generate the sources.

```
cd live
make clean; make sles
```

You can find the result in the `dist`directory. Now, fork and clone the [products/SLES](https://src.suse.de/products/SLES "‌") repository and copy the content of your `dist` directory to the `agama-installer-SLES` directory.

Now just create a PR. See [this example](https://src.suse.de/products/SLES/pulls/267 "‌") if you have any doubt.

---

## Submitting weekly snapshots

‌

- Check if all packages have been correctly submitted from `master` to OBS systemsmanagement:Agama:Devel project, all “submit *” GitHub actions should be green for the `master` branch. See [https://github.com/agama-project/agama/actions](https://github.com/agama-project/agama/actions "‌")
- Check that all packages in systemsmanagement:Agama:Devel project build correctly. See [https://build.opensuse.org/project/show/systemsmanagement:Agama:Devel](https://build.opensuse.org/project/show/systemsmanagement:Agama:Devel "‌")
- Copy the current state from `Devel` to `Release`:
  ```
  echo -n "agama agama-installer agama-auto agama-products agama-web-ui rubygem-agama-yast" | xargs -d " " -I % osc copypac systemsmanagement:Agama:Devel % systemsmanagement:Agama:Release
  ```
- Check that the packages build in [https://build.opensuse.org/project/show/systemsmanagement:Agama:Release](https://build.opensuse.org/project/show/systemsmanagement:Agama:Release "‌") and [https://build.suse.de/project/show/Devel:YaST:Agama:Release](https://build.suse.de/project/show/Devel:YaST:Agama:Release "‌") projects.
- Submit the packages to Factory
  ```
  echo -n "agama agama-installer agama-auto agama-products agama-web-ui rubygem-agama-yast" | xargs -d " " -I % osc sr -m "weekly release" systemsmanagement:Agama:Release % openSUSE:Factory
  ```
- Check if there are any declined old requests to SLES, close them first:
  ```
  echo -n "agama agama-auto agama-products agama-web-ui rubygem-agama-yast" | xargs -d " " -L 1 osc -A https://api.suse.de request list -s declined SUSE:SLFO:Main
  ```
- Submit the packages to SLFO:
  ```
  echo -n "agama agama-auto agama-products agama-web-ui rubygem-agama-yast" | xargs -d " " -I % osc -A https://api.suse.de sr -m "weekly release" Devel:YaST:Agama:Release % SUSE:SLFO:Main
  ```
- For submitting the Live ISO use the process described above
