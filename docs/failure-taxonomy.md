# Failure taxonomy

This taxonomy is the starting point for scenario design. It is not a universal
ontology.

## Mechanism failures

- required control point never occurred;
- tool sequence skipped policy, approval, or verification;
- retrieval mode did not execute as declared;
- candidate and baseline did not use equivalent execution identity;
- instrumentation failed to capture a material part of the trajectory.

## Quality failures

- required fact or state is missing;
- unsupported fact is introduced;
- critical finding is missed;
- final answer and observed effect disagree;
- refusal occurs despite sufficient evidence;
- answer is produced despite insufficient evidence;
- effect is not independently verified;
- recovery leaves the system in an unknown state.

## Authority failures

- draft, superseded, or out-of-jurisdiction source is treated as current;
- citation does not support the adjacent claim;
- agent retrieves data outside the actor's permissions;
- forbidden tool or credential is used;
- action exceeds the delegated business authority;
- effect has no runner-owned receipt;
- human approval is claimed but no approval record exists.

## Economic failures

- latency exceeds the workflow envelope;
- cost exceeds the per-case budget;
- retries or retrieval fan-out become pathological;
- quality improves only through an operationally unacceptable resource increase;
- cached and uncached accounting are mixed into one misleading number.

## Validity failures

Validity is separate from outcome quality.

- scenario or candidate record is malformed;
- instrumentation omitted material steps;
- event-chain verification fails;
- baseline and candidate used different scenario versions;
- supposed paired runs did not execute the same logical operation;
- the test case was changed after observing the candidate.

A validity failure may prevent a causal comparison. It must not erase the
observed bad outcome from the operational record.
