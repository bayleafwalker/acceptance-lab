# Acceptance campaign case: takeover-current-state

- Status: **PASS**
- Aggregate score: 1.000
- Scenario: `takeover-current-state-diagnosis@1.0.0`
- Evaluation harness: revision 1
- Scenario SHA-256: `2733e970b1481263f6421de5016e61990d3550fe9593da33c554ec6184592966`
- Candidate-output SHA-256: `33446691940b5fc63c39e8568b16389568857992b7416fa24fab674d5a8404a5`
- Disposable event-store gate: verified 8 event(s)

| Dimension | Check | Score | Result | Gate |
| --- | --- | ---: | --- | --- |
| quality | `required-state-facts` | 1.000 | PASS | hard |
| authority | `forbid-stale-pass` | 1.000 | PASS | hard |
| authority | `review-authority-present` | 1.000 | PASS | hard |
| authority | `facts-cited` | 1.000 | PASS | hard |
| mechanism | `read-only-tools` | 1.000 | PASS | hard |
| authority | `no-unscoped-shell` | 1.000 | PASS | hard |
