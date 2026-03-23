PACKAGES below come from config.obs_packages. It is a provisional list that
needs to be refined at one point.

Make agama-release-maker, a Python script, to

- [ ] submit $PACKAGES from systemsmanagement:Agama:Release to obs://home:mvidner:FakeFactory
- [ ] submit $PACKAGES from Devel:Yast:Agama:Release to Gitea mvidner:fake-slfo

Then,

- [ ] determine PACKAGES

With that, and having tested on the fake repos, add the production repos to agama-release-maker:

- [ ] submit $PACKAGES from systemsmanagement:Agama:Release to obs://openSUSE:Factory
- [ ] submit $PACKAGES from Devel:Yast:Agama:Release to Gitea pool:slfo
