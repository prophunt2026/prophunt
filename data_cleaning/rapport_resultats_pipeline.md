# Résumé final du pipeline de nettoyage (v2 - ML-compatible)

## 1. Données d’entrée et sorties finales

- Shape original : (7 230, 184)
- Shape vente nettoyée : (4 603, 68)
- Shape location : (628, 68)

## 2. Réduction des colonnes et lignes

- Colonnes supprimées : 116
- Colonnes conservées : 68
- Lignes supprimées total : 1 999
- Lignes vente : 4 603
- Lignes location : 628

## 3. Variable cible : transaction.prix (vente)

- Nombre de valeurs valides : 4 603
- Médiane : 370 000 TND
- Moyenne : 499 517 TND
- Skewness : 6.08

## 4. Effet sur la mémoire

- Mémoire originale : 71,9 MB
- Mémoire vente nettoyée : 26,3 MB
- Réduction mémoire : 63,5%

## 5. Structure des colonnes

- Colonnes numériques : 18
- Colonnes catégorielles : 50

## 6. Choix de conception du pipeline ML

- Encodage catégoriel laissé au pipeline ML, afin d’éviter toute fuite de données.
- OutlierClipper et RareCategoryMerger sont prévus pour être appliqués dans le pipeline ML.

## 7. Interprétation métier

- Le nettoyage a supprimé une grande partie des colonnes non utiles et des lignes redondantes.
- Le jeu de vente nettoyé est exploitable pour l’apprentissage supervisé.
- Le jeu de location reste plus petit, mais structuré pour des usages futurs.
- La réduction mémoire est importante, ce qui améliore la maniabilité du dataset dans un pipeline ML.

## 8. Conclusion

Le pipeline a produit des sorties conformes au schéma attendu et les résultats observés confirment une préparation de données propre, plus légère et mieux adaptée à l’apprentissage automatique.
