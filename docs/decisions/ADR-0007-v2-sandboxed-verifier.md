# ADR-0007: V2 verifier runs candidates in a locked-down Docker container

Status: accepted (2026-10-27)

## Decision
The property-test verifier gets a second backend, selected with
`sandbox="docker"` on `run_candidate` / `verify` and with `--sandbox docker`
on the worker service. The unchanged harness runs as
`python -I -S -c <harness>` inside a throwaway container of the official
`python:3.12-slim` image, pinned by digest (`SANDBOX_IMAGE` in
`python/frontier_py/verifiers/property_tests.py`). The container is started
with `--rm -i --pull never --network none --ipc none --read-only`, a 16 MiB
`noexec` tmpfs at `/tmp`, memory and swap capped at the task limit,
`--pids-limit 64 --cpus 1 --cap-drop ALL --security-opt no-new-privileges
--user 65534:65534`, core/nofile/fsize/cpu ulimits, no host mounts and no
host environment. Inputs go in on stdin and the nonce-tagged result line
comes back on stdout. Expected outputs are computed and compared in the
parent, as in V1. The parent enforces the wall timeout and runs
`docker kill` when it expires.

Receipts carry trust class `V2` only when the candidate actually ran in the
container. If the sandbox is unusable (no CLI, no Linux engine, image not
pulled, or `docker run` fails with status 125-127), the receipt is
`INCONCLUSIVE` with trust class `V1`, and its reason says the candidate was
not executed. The verifier never falls back silently to the unsandboxed
harness. The worker service refuses to start in `--sandbox docker` mode
without a usable sandbox. In that mode it also runs the extended
ground-truth check through the sandbox instead of in-process.

`VERIFIER_VERSION` stays `0.1.0` because the verification semantics are
unchanged. The backend is recorded in `trust_class` and in the receipt
`reason`.

## Why
V1 has no network or filesystem isolation (see the module docstring), so it
is only safe for the project's own DSL programs. Model-written code needs
OS-level isolation before any LLM worker is connected (errata, "Known
limitation"). Docker is on every GitHub-hosted Ubuntu runner and on typical
developer machines. Its flags give network, filesystem, privilege, memory,
process and CPU limits without extra tooling, and pinning the image by
digest makes the execution environment reproducible.

## Rejected
- **gVisor (`runsc`)**: a stronger boundary because syscalls are handled by
  a user-space kernel, but it is not installed on GitHub-hosted runners or
  Docker Desktop and needs daemon reconfiguration. It remains the natural
  hardening step: the same `docker run` line works with `--runtime runsc`.
- **nsjail / bubblewrap / firejail**: Linux-only, not preinstalled on CI
  images or developer hosts, and each has its own configuration surface that
  we would have to maintain and audit. firejail is setuid-root and aimed at
  desktop applications, so its attack surface is a poor fit for a verifier.
- **Python-level sandboxing (restricted builtins, audit hooks, seccomp from
  inside the child)**: these can be bypassed from inside the same
  interpreter, so they provide no isolation boundary.
- **Silent fallback to V1 when docker is missing**: this would let a receipt
  overstate its isolation. Failing closed is required by ADR-0004.
- **Native Windows isolation (Job Objects, AppContainer, Windows
  containers)**: the V1 harness on Windows enforces timeouts only. Windows
  containers need a different base image and give different guarantees.
  On Windows, V2 is available only through Docker Desktop's Linux engine,
  where the container runs in the WSL2/Hyper-V utility VM. The integration
  tests are therefore qualified on Linux CI (`verifier-v2` job).

## Consequences and caveats
- A container shares the host kernel, so it is not a VM boundary. A kernel
  exploit escapes, and without user-namespace remapping it lands as uid
  65534 on the host.
- The image must be pulled ahead of time (`docker pull <SANDBOX_IMAGE>`),
  because runs use `--pull never` so that the network and registry are never
  touched at verification time.
- Container start-up adds roughly a second per verification and a fixed
  `DOCKER_STARTUP_GRACE_S` to the parent's wall timeout.
- A candidate can still forge a result line by finding the nonce in its own
  memory. As in V1, the defence is that the parent compares outputs against
  expected values the candidate never sees. A candidate that exits with
  status 125-127 is reported `INCONCLUSIVE` rather than `FAIL`, never `PASS`.
- Refresh the pinned digest as described next to `SANDBOX_IMAGE`. The
  digest is the multi-architecture index digest.
