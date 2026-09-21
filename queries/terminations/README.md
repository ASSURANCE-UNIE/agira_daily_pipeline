# Terminations SQL

Put the production query in `query.sql`.
It must use the bound parameter `:target_date` and return one row per termination
whose effective termination date is exactly that date.

Until the source schema is supplied, the stable integration contract is one
column named `record_json`. Its value must be a JSON object matching
`agira_api.models.TerminationRecord`. This avoids guessing how contracts,
persons, claims, and vehicles are joined. Once the real SQL is available, a
typed row mapper can replace this boundary without changing archives or depots.
