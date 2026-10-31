# Publishing a Docker image

This guide is for BirdFrame maintainers publishing an image to
`ghcr.io/simenf/birdframe`. To update an existing installation, follow the
[installation upgrade instructions](installation.md#upgrading) instead.

Publishing is currently manual: merging to `master`, pushing a Git tag, or
creating a GitHub release does not build or publish an image. The `docker/`
directory contains the container entrypoint; the release instructions live in
`docs/` with the other maintainer guides.

## Prepare the release

1. Review the [release checklist](development.md#release-checklist), run the
   source checks, and plan the clean-install, upgrade, architecture, and TV
   checks for the published image.
2. Update the version in `backend/birdframe/__init__.py`,
   `backend/pyproject.toml`, `frontend/package.json`,
   `frontend/package-lock.json`, `.env.example`, and `docker-compose.yml`.
   Move the relevant changelog entries into the new version and write release
   notes.
3. Merge the reviewed release commit to `master`. On the build machine, check
   out and fast-forward `master`, then verify the commit and a clean working
   tree. Build from the repository root so the image uses that exact source.

   ```sh
   git switch master
   git pull --ff-only origin master
   git status --short
   git rev-parse HEAD
   ```

   Review untracked files as well as modifications: files in the build context
   that are not excluded by `.dockerignore` can affect the image.

## Authenticate and check the builder

Start Docker Engine or Docker Desktop. The publishing account needs permission
to write the `birdframe` package. If Docker is not already signed in to GHCR,
create a GitHub personal access token **(classic)** with `write:packages`, then
run the command below and paste the token at the password prompt. See
[GitHub's container registry authentication guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).

```sh
docker login ghcr.io -u simenf
docker buildx version
docker buildx inspect --bootstrap
```

The builder must support both `linux/amd64` and `linux/arm64`, either natively
or through emulation. If the selected builder cannot build both, configure a
multi-platform builder using [Docker's instructions](https://docs.docker.com/build/building/multi-platform/).

## Build and publish the versioned image

Set the version to the one prepared above; `0.1.3` here is only an example.
Run these commands from the clean, merged checkout:

```sh
BIRDFRAME_RELEASE_VERSION=0.1.3
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag "ghcr.io/simenf/birdframe:${BIRDFRAME_RELEASE_VERSION}" \
  --push .
```

`--push` publishes the image to GHCR; it does not necessarily load a local
image. Inspect the published manifest and confirm that it lists both platforms:

```sh
docker buildx imagetools inspect "ghcr.io/simenf/birdframe:${BIRDFRAME_RELEASE_VERSION}"
```

Pull the versioned tag and smoke-test it on both architectures, including an
upgrade with existing data and packages. Check the application version, health
endpoint, artwork, and the detection and display workflows relevant to the
release. Verify the package is publicly accessible if it is intended for public
installation. See [Docker's image inspection reference](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/).

## Promote and announce

Once the versioned image passes verification, point `latest` at that same
published image and inspect it:

```sh
docker buildx imagetools create \
  --tag ghcr.io/simenf/birdframe:latest \
  "ghcr.io/simenf/birdframe:${BIRDFRAME_RELEASE_VERSION}"
docker buildx imagetools inspect ghcr.io/simenf/birdframe:latest
```

Confirm `HEAD` is still the tested release commit, then create and push an
annotated Git tag:

```sh
git rev-parse HEAD
git tag -a "v${BIRDFRAME_RELEASE_VERSION}" -m "BirdFrame ${BIRDFRAME_RELEASE_VERSION}"
git push origin "v${BIRDFRAME_RELEASE_VERSION}"
```

Publish release notes if desired. The Git tag and GitHub release are separate
from the container image and do not publish it automatically. Communicate the
new image tag and link to the [upgrade instructions](installation.md#upgrading):
existing containers do not replace themselves, and installations pinned to an
older `BIRDFRAME_VERSION` continue to use that version until it is changed.
