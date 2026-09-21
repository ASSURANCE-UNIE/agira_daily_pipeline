-- The pipeline binds the target-date parameter to the processing date minus
-- the configured question lag (one calendar day by default).
SELECT
    con.idcontrat,
    con.numero_police,
    -- AGIRA fixed widths: name 20, first name 12.
    LEFT(TRIM(per.nom), 20) AS nom,
    LEFT(TRIM(per.prenom), 12) AS prenom,
    per.date_naissance,
    ap.code_postal,
    per.permis_date_obtention,
    COALESCE(
        last_registration.immatriculation,
        ra.immatriculation
    ) AS immatriculation,
    per.est_personne_morale,
    -- AGIRA wants a 9-digit SIREN; pmorale_rcs sometimes holds a 14-digit
    -- SIRET (SIREN is its first 9 digits) or free text, which is dropped.
    CASE
        WHEN per.pmorale_rcs ~ '^\d{9}(\d{5})?$' THEN LEFT(per.pmorale_rcs, 9)
    END AS siren
FROM contrat con
JOIN personne per
    ON per.idpersonne = con.idpersonne
JOIN adresse_personne ap
    ON ap.idadresse_personne = f_idadresse_principale_active(per.idpersonne)
JOIN avenant avt
    ON avt.idavenant = f_idavenant_dernier(con.idcontrat, FALSE)
JOIN adhesion adh
    ON adh.idavenant = avt.idavenant
JOIN risque_auto ra
    ON ra.idadhesion = adh.idadhesion
LEFT JOIN LATERAL (
    SELECT history.immatriculation
    FROM historique_immatriculation history
    WHERE history.idrisque_auto = ra.idrisque_auto
    ORDER BY
        history.date_saisie DESC,
        history.idhistorique_immatriculation DESC
    LIMIT 1
) AS last_registration ON TRUE
WHERE con.date_creation::date = :target_date
  AND (con.est_projet = FALSE OR con.est_projet IS NULL)
  AND con.est_sans_effet_niveau = 0
  AND (avt.est_projet = FALSE OR avt.est_projet IS NULL)
  AND (adh.est_projet = FALSE OR adh.est_projet IS NULL)
ORDER BY con.idcontrat, ra.idrisque_auto;
