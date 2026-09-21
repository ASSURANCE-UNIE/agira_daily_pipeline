# Questions SQL

Put the production query in `query.sql`. It must use the bound parameter
`:target_date` and return one row per new policy on that date.

Required/recognized aliases:

- `idcontrat`, `numero_police`, `nom`, `prenom`, `date_naissance`
- `code_postal`, `permis_date_obtention`, `immatriculation`
- `est_personne_morale`, `siren`
- optional: `previous_insurer_company_code`, `previous_contract_number`

Natural persons produce every applicable AGIRA correspondence family. Legal
entities omit personal birth/licence fields and use registration and/or SIREN.
