-- The pipeline binds the target-date parameter to the processing date minus
-- 35 calendar days.
-- Matching the last (non-draft) avenant's date_fin to it publishes the
-- termination 35 days later.
SELECT
    json_build_object(
        'operation', 'create',
        'company_record_id', rd.idresiliation_demande::text,
        'record_company', json_build_object(
            'country_code', '250',
            'company_code', '0703',
            'internal_company_code', 'ASSUN'
        ),
        'contract', json_build_object(
            'insurer', json_build_object(
                'country_code', '250',
                'company_code', '0703',
            	'internal_company_code', 'ASSUN'
            ),
            'contract_number', cont.numero_police,
            'effective_date', avtpremier.date_effet::date,
            'bonus_malus_coefficient', (
                SELECT REPLACE(
                    TO_CHAR(ei.valeur_indice, 'FM0.00'),
                    '.',
                    ','
                )
                FROM evolution_indice ei
                WHERE ei.idcontrat = cont.idcontrat
                ORDER BY ei.date_maj DESC
                LIMIT 1
            )
        ),
        'persons', json_build_array(
            json_build_object(
                'role', 'subscriber',
                'person_kind',
                    CASE
                        WHEN assure.est_personne_morale IS TRUE THEN 'legal_entity'
                        ELSE 'natural_person'
                    END,
                -- AGIRA fixed widths: name 20, first name 12.
                'name_or_company_name', LEFT(TRIM(assure.nom), 20),
                'first_name',
                    CASE
                        WHEN assure.est_personne_morale IS TRUE THEN NULL
                        ELSE LEFT(TRIM(assure.prenom), 12)
                    END,
                'birth_date',
                    CASE
                        WHEN assure.est_personne_morale IS TRUE THEN NULL
                        ELSE assure.date_naissance::date
                    END,
                -- AGIRA fixed width: 32 per address line.
                'address_lines', ARRAY(
                    SELECT LEFT(TRIM(address_line), 32)
                    FROM unnest(
                        ARRAY[
                            assure_adr.ligne1,
                            assure_adr.ligne2,
                            assure_adr.ligne3,
                            assure_adr.rue
                        ]
                    ) AS address_line
                    WHERE NULLIF(TRIM(address_line), '') IS NOT NULL
                ),
                'postal_code', assure_adr.code_postal,
                'city', LEFT(TRIM(assure_adr.ville), 26),
                -- AGIRA width is 12; longer legacy/NEPH-prefixed numbers are
                -- omitted rather than truncated into a wrong identifier.
                'driving_licence_number',
                    CASE
                        WHEN assure.est_personne_morale IS TRUE THEN NULL
                        WHEN LENGTH(TRIM(assure.permis_numero)) > 12 THEN NULL
                        ELSE TRIM(assure.permis_numero)
                    END,
                'driving_licence_date',
                    CASE
                        WHEN assure.est_personne_morale IS TRUE THEN NULL
                        ELSE assure.permis_date_obtention::date
                    END
            )
        ),
        'termination', json_build_object(
            'reason_code',
                CASE
                    -- Cancellation by the insurer / contract nullity.
                    WHEN avt_dernier.idavenant_fin IN (26, 11, 20) THEN '1'
                    -- Cancellation by the insurer for non-payment.
                    WHEN avt_dernier.idavenant_fin = 1 THEN '2'
                    -- Cancellation by the insured or disappearance of the risk.
                    WHEN avt_dernier.idavenant_fin IN (
                        23, 24, 27, 6, 7, 8, 15, 14,
                        31, 2, 30, 28, 19, 21, 9, 13
                    ) THEN '5'
                    ELSE '4'
                END,
            'termination_date', avt_dernier.date_fin::date
        ),
        'claims', COALESCE(claim_data.claims, json_build_array()),
        'vehicle', json_build_object(
            'category_code', '0',
            'registration_number', (
                SELECT hi.immatriculation
                FROM historique_immatriculation hi
                WHERE hi.idrisque_auto = ra.idrisque_auto
                ORDER BY hi.date_saisie DESC
                LIMIT 1
            )
        )
    ) AS record_json
FROM resiliation_demande rd
JOIN contrat cont
    ON cont.idcontrat = rd.idcontrat
JOIN avenant avt
    ON avt.idavenant = f_idavenant_actif(cont.idcontrat)
JOIN avenant avtpremier
    ON avtpremier.idavenant = f_idavenant_premier(cont.idcontrat)
-- Last avenant by date_effet. Second argument excludes drafts (est_projet),
-- which have no date_fin and would otherwise drop the termination.
JOIN avenant avt_dernier
    ON avt_dernier.idavenant = f_idavenant_dernier(cont.idcontrat, false)
JOIN personne assure
    ON assure.idpersonne = cont.idpersonne
JOIN produit prd
    ON prd.idproduit = avt.idproduit
JOIN personne cie
    ON cie.idpersonne = prd.idpersonne
JOIN adresse_personne assure_adr
    ON assure_adr.idadresse_personne = f_idadresse_principale_active(assure.idpersonne)
JOIN adhesion adh
    ON adh.idadhesion = f_idadhesion_actif(cont.idcontrat, avt.date_effet)
JOIN risque_auto ra
    ON ra.idadhesion = adh.idadhesion
LEFT JOIN LATERAL (
    SELECT json_agg(
        claim_row.claim_json
        ORDER BY claim_row.claim_date, claim_row.open_guarantee_id
    ) AS claims
    FROM (
        SELECT
            sin.date_survenance AS claim_date,
            sgo.idsinistre_garantie_ouverte AS open_guarantee_id,
            json_build_object(
                'claim_number', sin.numero_cie::text,
                'nature_code',
                    CASE
                        WHEN claim_nature.code_natsin = 'CORPO' THEN 'C'
                        ELSE 'M'
                    END,
                'claim_date', sin.date_survenance::date,
                'guarantee_code',
                    CASE
                        WHEN UPPER(gc.code) LIKE 'RC%' THEN '01'
                        WHEN UPPER(gc.code) IN ('VOL', 'VI') THEN '04'
                        WHEN UPPER(gc.code) = 'INC' THEN '05'
                        WHEN UPPER(gc.code) IN ('BDG', 'BG') THEN '06'
                        WHEN UPPER(gc.code) = 'DTA' THEN '07'
                        ELSE '99'
                    END,
                'responsibility_percent',
                    responsibility.valeur
            ) AS claim_json
        FROM sinistre_garantie_ouverte sgo
        JOIN sinistre sin
            ON sin.idsinistre = sgo.idsinistre
        JOIN cotisation_ventilation cv
            ON cv.idcotisation_ventilation = sgo.idcotisation_ventilation
        JOIN garantie_tarif gt
            ON gt.idgarantie_tarif = cv.idgarantie_tarif
        JOIN garantie_cie gc
            ON gc.idgarantie_cie = gt.idgarantie_cie
        LEFT JOIN zsys_nature_sinistre claim_nature
            ON claim_nature.idnature_sinistre = sin.idnature_sinistre
        LEFT JOIN zsys_sinistre_taux_resp responsibility
            ON responsibility.idsinistre_taux_resp = sin.idsinistre_taux_resp
        WHERE sin.idcontrat = cont.idcontrat
          AND sin.date_survenance::date >= avtpremier.date_effet::date
          AND sin.date_survenance::date <= avt_dernier.date_fin::date
          AND (sin.est_projet = FALSE OR sin.est_projet IS NULL)
          AND (sin.est_efface = FALSE OR sin.est_efface IS NULL)
          AND (sgo.est_annulee = FALSE OR sgo.est_annulee IS NULL)
    ) AS claim_row
) AS claim_data ON TRUE
WHERE avt_dernier.date_fin::date = :target_date
  AND rd.statut_demande = 'V'
  AND rd.est_valide_controle IS TRUE
  AND avt_dernier.idavenant_fin IS NOT NULL
  -- AGIRA requires a birth date for natural persons and at least one address
  -- line; an incomplete person record must not abort the whole day's file.
  AND (assure.est_personne_morale IS TRUE OR assure.date_naissance IS NOT NULL)
  AND COALESCE(
        NULLIF(TRIM(assure_adr.ligne1), ''), NULLIF(TRIM(assure_adr.ligne2), ''),
        NULLIF(TRIM(assure_adr.ligne3), ''), NULLIF(TRIM(assure_adr.rue), '')
      ) IS NOT NULL
ORDER BY rd.date_saisie DESC
LIMIT 100000;