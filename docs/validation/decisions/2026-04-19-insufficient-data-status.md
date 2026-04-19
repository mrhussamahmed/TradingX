# Insufficient Data Status Decision

## Question

Review item `L5` asked whether a validation criterion with insufficient data
should report `pending` or `fail`.

## Audit

- `GATES-0001` does not currently mandate `fail` for missing evidence.
- Existing Stage 3 readiness documents already use `pending` to mean
  "criterion not yet falsified, but evidence is not sufficient to pass."
- The current validation flow distinguishes between an evaluated failed
  criterion and a criterion that cannot yet be evaluated honestly.

## Decision

No code change in this wave. Insufficient-data conditions remain `pending`
until `GATES-0001` says otherwise.

## Follow-up

If later gate policy wants missing evidence to hard-fail, update
`docs/validation/acceptance_gates.md` first and then tighten the validator.
