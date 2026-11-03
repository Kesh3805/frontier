# ADR-0009: Warm verification with pre-spawned, single-use children

Status: proposed (2026-11-04). This is a prototype. No result depends on it.

## Context
exp-009 ([results](../../results/exp-009/README.md)) measured that about
92% of a V1 verification's wall time on the Windows dev host is fixed
per-call overhead: about 120 ms of about 130 ms. Most of it is starting a
new `python -I -S -c <harness>` child for each candidate. Early stopping
cannot remove that overhead, but reusing a warm interpreter might. Reuse
weakens the per-candidate process boundary, though, so this ADR records
what each option gives up before any warm mode is used for a result.

## Decision
Add an opt-in warm mode for `sandbox="none"`:
`verify(..., prespawn=PrespawnPool(size=n))` and the same keyword on
`run_candidate` (`python/frontier_py/verifiers/property_tests.py`).

- The pool starts the same V1 child that a cold run starts: the same argv,
  environment allowlist, POSIX rlimits and session, and a fresh temporary
  cwd. Cold runs and the pool share one function, `_v1_popen`.
- A pre-spawned child boots, imports the harness's modules and then blocks
  reading stdin. It holds no nonce, inputs or source until it is taken.
- `take` hands out one child and at once starts a replacement in a
  background thread. Up to `size` children per (memory, CPU) limit pair are
  starting or idle.
- Each child serves exactly one candidate and is then reaped, as in a cold
  run. A child that died while idle is discarded and never handed out.
- The protocol is unchanged: a per-run nonce, a duplicated result
  descriptor with fd 0/1/2 pointed at the null device, and expected outputs
  computed and compared only in the parent.
- Receipts stay trust class V1. Their `reason` carries a distinct note that
  says the child was prespawned.
- The default (`prespawn=None`) is unchanged. On the existing correct and
  adversarial candidate lists, default receipts are byte-identical to
  `main`'s.

## Threat model

| | V1 cold (default) | Warm: pre-spawned single-use (this ADR) | V2 docker |
|---|---|---|---|
| Process per candidate | yes, fresh | yes, fresh, started earlier | yes, fresh container |
| Interpreter state shared between candidates | none | none | none |
| Candidate can reach a *later* candidate's process | Windows: yes, by leaving an orphaned process (no job object; `taskkill /T` follows only live parent links). POSIX non-root: no (`RLIMIT_NPROC = 0`, whole session killed). | Windows: yes, as cold. POSIX: **yes, newly**: the next child is alive and idle while this candidate runs, as the same user. | no (separate container, `--pids-limit`, no shared IPC/PID namespace) |
| Network / filesystem isolation | none | none | yes |
| Wall timeout covers interpreter start-up | yes | no (start-up already happened) | yes, plus a grace period |

What a running candidate A can do to an idle pre-spawned child B on POSIX,
as the same uid:

- **Kill it.** If B dies while idle, `take` notices and starts a fresh
  child. If B is killed mid-run (only possible with `size > 1` or with
  concurrent verifications), that candidate's verdict becomes FAIL
  ("exited without a result") or INCONCLUSIVE.
- **Open `/proc/B/fd/0` or `/proc/B/fd/1`** (needs `PTRACE_MODE_READ`,
  which Yama does not restrict) and write into B's stdin or result pipe.
  B then reads a corrupted request and fails, never sees end of file and
  times out, or its result channel carries an extra line. The effect is a
  false FAIL or INCONCLUSIVE for the next candidate. In sequential use A
  cannot forge that candidate's result line this way, because B's nonce is
  chosen by the parent after A has exited. The parent-side comparison
  against expected outputs stays the defence against a forged PASS.
- **ptrace B, or write `/proc/B/mem`.** This needs `PTRACE_MODE_ATTACH`,
  which is blocked when Yama `ptrace_scope >= 1` (the Ubuntu default) and
  allowed at scope 0. With it, A could patch B's harness. V1 does not hide
  the reference sources from the candidate, so a false PASS for the next
  candidate is then possible in principle.

On Windows, a same-user process can already open and write another one, and
cold V1 cannot stop A from leaving an orphan that does the same to later
children. Warm mode widens that window there but adds no new kind of attack.
On POSIX it removes the "no survivor" property that cold V1 has for non-root
users. That is the cost this ADR accepts for an opt-in mode.

It is acceptable only because of the existing scope rule: V1 is cleared
only for the project's own DSL programs, and model-written code needs V2
(ADR-0007 and the errata). Warm mode does not change what V1 may be used
for. Its intended use is measurement: how much of exp-009's overhead is
start-up latency.

### State that would leak in a reused process
These are the reasons a persistent child is rejected below. Each item is
reachable by a candidate of a few lines.

- **`sys.modules` and module globals:** patching `json.dumps`, `os.write`
  or `time.monotonic` changes the harness and every later candidate. The
  existing `MONKEYPATCH` test candidate does exactly this.
- **`builtins`:** `builtins.sorted = ...` makes a later wrong candidate
  agree with a wrong expectation, or a later correct one fail.
- **Threads:** a non-daemon thread survives the candidate's return. It can
  read the next candidate's hidden inputs and namespace, rewrite its
  function, or race its outputs. Python threads cannot be killed.
- **File descriptors:** a descriptor left open, or a `dup` of the result
  descriptor, lets a later write land on the next candidate's channel.
- **Irreversible hooks:** `sys.addaudithook` cannot be removed;
  `sys.settrace`/`setprofile`, `signal` handlers, `atexit`, `gc` callbacks
  and finalizers on long-lived objects can be.
- **Process limits and environment:** `setrlimit` can only be lowered, so
  limits ratchet down; `RLIMIT_CPU` is cumulative over the process's life;
  cwd contents, `os.environ`, `sys.path`, the recursion limit and the
  `random` state all persist.
- **C-level state through `ctypes`:** arbitrary interpreter memory,
  including the next nonce once it is received.

No reset routine can be shown to be complete against this list. Threads and
audit hooks alone make a reliable cross-candidate false PASS
straightforward.

## Options considered
1. **Persistent child per task, reset between candidates.** This removes
   the most overhead: no process start-up at all. It is rejected because
   reuse turns every item in the list above into a cross-candidate attack,
   including a false PASS, on every platform.
2. **Fork server (POSIX).** A pristine, pre-imported zygote forks one
   child per candidate. Each candidate still gets its own process, and the
   copy-on-write image saves exec and interpreter initialisation. It is
   rejected for now:
   - it does not exist on Windows, which is where exp-009 measured the
     overhead;
   - `fork` in a process with threads is unsafe, so the zygote must stay
     single-threaded;
   - every child inherits the zygote's address-space layout, hash seed and
     `random` state, so candidates are not independent;
   - the zygote is a long-lived process that a candidate could attack as
     the same uid, as with the idle child above.
   It is the natural next step for Linux if pre-spawning turns out to be
   insufficient there.
3. **Pool of pre-spawned, single-use children (chosen).** This keeps one
   fresh process per candidate, the same argv, environment and limits as
   cold V1, and the same protocol. It works on Windows and POSIX. It hides
   start-up latency instead of removing start-up work, so its benefit
   depends on slack: there must be time between calls (worker time, parent
   work) or enough pool depth and free cores to boot children in parallel.
   For back-to-back calls, `size` must be about start-up time divided by
   per-call time.
4. **Subinterpreters, or batching several candidates in one child.** These
   are not process boundaries. Both have option 1's problems.

The starting hypothesis was that pre-spawned single-use children are the
best trade. It holds, with one correction: they are not "free" isolation-
wise on POSIX, for the reason given under Threat model.

## Consequences and caveats
- **Wall-clock cost:** wall-clock `cost_units` fall in warm mode.
  `charge_per_case` charges and verdicts do not change. The equivalence
  test covers the existing correct and adversarial lists, with and without
  `early_stop`.
- **Wall timeout:** it no longer includes interpreter start-up, so a
  candidate within roughly one start-up time of the wall limit may PASS
  warm and be INCONCLUSIVE cold. Per-call timeouts are enforced inside the
  child and are unchanged.
- **CPU contention:** start-up CPU is still spent, and with `size > 1` it
  runs concurrently with the candidate under test. On a loaded host this
  can push a borderline candidate over its per-call timeout.
- **POSIX `preexec_fn`:** the pool calls `Popen` (with `preexec_fn` on
  POSIX) from a background thread. CPython documents `preexec_fn` as unsafe
  when other threads exist. A deadlock before exec would show up as a wall
  timeout (INCONCLUSIVE), never as a PASS.
- **Child CPU stats:** on POSIX they include the discarded child, in the
  rare case that one is reaped inside `take`.
- **Docker:** V2 is out of scope here (`prespawn` with `sandbox="docker"`
  raises). Pre-creating containers would attack V2's larger start-up cost
  and needs its own analysis.
- **Before warm mode is used for a preregistered result,** at least:
  - make the idle child non-dumpable on Linux (`PR_SET_DUMPABLE = 0`, which
    closes `/proc/B/fd` and `/proc/B/mem` to other same-uid processes),
    accepting that this makes the child's start-up differ from cold V1;
  - record the warm mode, and the pool size, in the run manifest.
- **Measurements:** an informal dev timing script is
  `scripts/time_warm_verifier.py`. Its numbers are not a finding: a finding
  needs a frozen preregistration.
