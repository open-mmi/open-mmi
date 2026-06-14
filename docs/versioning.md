# Versioning

`open-mmi` uses conservative versioning because the project interfaces with real vehicles.

## Current status

The project is currently alpha/backend software.

The current Python package version is:

```text
0.1.0a1
```

Future public GitHub Releases should use names such as:

```text
v0.1.0-alpha.1
v0.1.0-alpha.2
v0.1.0-beta.1
v0.1.0
```

## Historical tags

Earlier tags such as:

```text
v1.0.0-backend
v1.0.0-backend-candidate
```

are historical backend checkpoints.

They do not represent a final Open MMI v1 product release.

## Tags and GitHub Releases

A git tag is a source checkpoint.

A GitHub Release is a public artefact for users and contributors. It should include release notes, known limitations, screenshots or example output where relevant, and a clear source checkpoint.

## Release rule

A GitHub Release should only be created when the release has:

* a source tag
* release notes
* known limitations
* tested install/update path
* tested reference vehicle notes
* screenshots or example output where relevant
* clear alpha/beta/stable status

See [`release-checklist.md`](release-checklist.md) before creating a GitHub Release.

## Versioning goal

Version numbers should describe project maturity honestly.

Until open-mmi has a polished user-facing UI, broader testing, clearer packaging, replay/demo tooling, and multiple validated profiles, it should remain in `0.x` alpha/beta versioning.
