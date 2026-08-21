# DTU advertisement smoke tests

These are **Digital Twin Universe (DTU) profiles** that prove — in a clean, isolated
container — that installing `claim-guard` the way a real user would actually composes and
**advertises its contributions** for each install shape. They are the DTU-native analogue of
a smoke test: **composition/advertisement only, no `pytest`, no module unit tests.**

Each profile installs Amplifier + the anthropic provider, installs the bundle-under-test from
public GitHub `@main`, runs a single advertisement probe (`amplifier run --mode single`) that
asks the composed session to enumerate its own `claim-guard:*` agents / `claim_ledger` tool /
`/claim-guard` mode / mode+recipes+lsp tools, and then **self-proves** by `grep`-ing that output
in a `readiness` check — so `check-readiness` returning `ready: true` **is** the PASS.

| Profile | Install shape | Proves |
|---|---|---|
| `profiles/claim-guard-behavior-app.yaml` | **behavior** `--app` (recommended) | 7 `claim-guard:*` agents + `claim_ledger` (15 ops) + `/claim-guard` mode + mode/recipes/lsp tools, layered onto `foundation` |
| `profiles/claim-guard-root-bundle.yaml` | **root bundle** standalone (`bundle use`) | the **identical** 7-agent set — proof the behavior is self-sufficient (behavior `--app` ≡ root bundle) |
| `profiles/claim-guard-probing-app.yaml` | **probing behavior** `--app` (full / Phase-2) | 10 agents (7 + probe-designer/pen-tester/regression-graduator) + the delegatable execution primitives (`digital-twin-universe:dtu-profile-builder`, `parallax-discovery:antagonist`, `amplifier-tester:setup-digital-twin`) |

## Requirements

- `amplifier-digital-twin` (the DTU CLI) available on the host, with Incus configured.
- `ANTHROPIC_API_KEY` in the host environment — forwarded into the DTU via `passthrough`.
  The advertisement probe makes **one** real LLM call per shape to enumerate the composed
  surface. The key is only ever referenced as `${ANTHROPIC_API_KEY}` / `key_env`; it is never
  written into a profile.

## Run one

```bash
amplifier-digital-twin launch dtu/profiles/claim-guard-behavior-app.yaml --name cg-shapeA
amplifier-digital-twin check-readiness cg-shapeA          # -> ready:true  == PASS
amplifier-digital-twin exec cg-shapeA -- cat /root/advertisement.txt   # human-readable evidence
amplifier-digital-twin destroy cg-shapeA
```

Swap the profile for `claim-guard-root-bundle.yaml` or `claim-guard-probing-app.yaml` to prove
the other shapes. Each profile's leading comment block documents its exact launch invocation and
expected advertised set.

> **Why ship these with the product?** The install shape (behavior `--app` vs root bundle) is a
> load-bearing contract of this bundle, and it drifts silently (a behavior that isn't
> self-sufficient composes *nothing* under `--app` with no error). These profiles are the
> reproducible, self-proving check that the contract still holds — validation artifacts, so they
> live in the repo alongside the code they validate.
