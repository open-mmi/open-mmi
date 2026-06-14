# Release checklist

A GitHub Release is a public artefact for users and contributors.

A git tag is only a source checkpoint. Do not create a GitHub Release unless the project state is clear, tested, and honestly documented.

## Required before a GitHub Release

- [ ] release is created from a source tag
- [ ] version number matches the release notes
- [ ] README status wording is accurate
- [ ] known limitations are listed
- [ ] install path has been tested from a fresh checkout
- [ ] update path has been tested where relevant
- [ ] uninstall path has been tested where relevant
- [ ] daemon starts cleanly
- [ ] logs are readable
- [ ] status snapshot is generated
- [ ] status dashboard or UI consumer works
- [ ] security policy is current
- [ ] licence is present and accurate
- [ ] release notes include clear alpha/beta/stable status

## Reference vehicle notes

For any release claiming vehicle support:

- [ ] vehicle make/model/year/platform is listed
- [ ] tested profile is listed
- [ ] tested capture point is listed
- [ ] tested CAN adapter is listed, if relevant
- [ ] tested bitrate is listed, if known
- [ ] decoded states are listed
- [ ] unsupported or untested states are listed
- [ ] safety limitations are stated

## Screenshots or example output

Include at least one of:

- [ ] CLI dashboard screenshot
- [ ] graphical UI screenshot
- [ ] daemon status/log output
- [ ] example `status.json`
- [ ] replay/demo output, once available

Screenshots must be labelled honestly as alpha, beta, or stable.

## Release notes should include

- release name and version
- source tag
- project maturity status
- tested environment
- tested vehicle/profile, if applicable
- highlights
- known limitations
- upgrade notes
- safety/security notes
- contribution notes

## Do not release if

- README claims are ahead of tested behaviour
- current source does not match the release
- generated artefacts cannot be traced back to source
- known safety issues are undocumented
- install or startup is broken
- limitations are unclear
