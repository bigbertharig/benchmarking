# Docker Assets

This repo keeps Docker build definitions for local rig use, but the `docker/`
directory is gitignored so large local image tarballs do not get published.

## Layout

- `docker/bench-code/`
- `docker/bench-knowledge/`
- `docker/bench-pipeline/`
- `docker/bench-reasoning/`
- `docker/images/`

`docker/images/` is for local exported images such as `bench-code.tar.gz`.

## Rebuild

Rebuild images locally from the checked-in Dockerfiles:

```bash
docker build -t bench-code docker/bench-code
docker build -t bench-knowledge docker/bench-knowledge
docker build -t bench-pipeline docker/bench-pipeline
docker build -t bench-reasoning docker/bench-reasoning
```

Export them if you want local cached tarballs:

```bash
mkdir -p docker/images
docker save bench-code | gzip > docker/images/bench-code.tar.gz
docker save bench-knowledge | gzip > docker/images/bench-knowledge.tar.gz
docker save bench-pipeline | gzip > docker/images/bench-pipeline.tar.gz
docker save bench-reasoning | gzip > docker/images/bench-reasoning.tar.gz
```

Load a saved image:

```bash
docker load < docker/images/bench-code.tar.gz
```

The public repo should contain the Dockerfiles and docs needed to reproduce the
local images, not the exported image archives themselves.
