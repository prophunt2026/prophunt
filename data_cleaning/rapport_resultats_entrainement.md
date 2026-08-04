# Rapport final de la phase d’entraînement ML

## 1. Contexte et artefacts générés

La phase d’entraînement a été exécutée sur le jeu de données nettoyé `cleaned_vente.csv` avec une stratégie de validation robuste en trois sous-ensembles : train/validation/test.

Artefacts produits par l’exécution :

- `best_model.joblib` : modèle retenu pour l’inférence
- `preprocessor.joblib` : pipeline de preprocessing appris sur le jeu d’entraînement
- `training_results.json` : récapitulatif structuré des métriques, hyperparamètres et validations
- `visualizations/` : série de diagnostics graphiques du comportement du modèle

## 2. Données et découpage utilisé

- Nombre d’échantillons : 4 566
- Nombre de features après préparation : 32
- Répartition des splits :
  - Entraînement : 2 739
  - Validation : 913
  - Test : 914
- Temps d’entraînement total : 227,95 secondes

## 3. Modèle retenu

Le meilleur modèle final sélectionné est : `LightGBM`.

Hyperparamètres retenus :

- `learning_rate = 0.04`
- `max_depth = 8`
- `num_leaves = 55`
- `n_estimators = 250`
- `min_child_samples = 10`
- `colsample_bytree = 0.95`
- `subsample = 0.9`
- `reg_alpha = 0.05`
- `reg_lambda = 10.0`

Ce choix est cohérent avec les résultats de la grille d’hyperparamètres et la comparaison croisée par modèle, où le LightGBM domine nettement les autres candidats sur la stabilité globale.

## 4. Résultats quantitatifs de performance

### 4.1 Métriques de validation sur les sous-ensembles

| Sous-ensemble | RMSE | MAE | R2 | MAPE | MedAE |
|---|---:|---:|---:|---:|---:|
| Train | 339 824.84 | 131 183.57 | 0.5307 | 113.83 | 61 860.23 |
| Validation | 414 957.23 | 168 049.68 | 0.3906 | 88.26 | 77 621.84 |
| Test | 427 907.38 | 170 018.55 | 0.4191 | 164.09 | 64 798.66 |

### 4.2 Interprétation seuils métier

Les objectifs métier définis dans le rapport de validation sont les suivants :

- RMSE cible : 80 000 TND
- MAE cible : 50 000 TND
- R2 cible : 0.75
- MAPE cible : 20%
- MedAE cible : 35 000 TND

Résultat observé :

- Aucun seuil cible n’est atteint sur le test hold-out.
- La qualité prédictive est donc insuffisante pour une utilisation en production sans amélioration supplémentaire.

## 5. Analyse du surapprentissage et stabilité

L’écart entre train et test est modéré, mais non négligeable.

### 5.1 Gap train/test

- RMSE : train 339 824.84 vs test 427 907.38, écart = 88 082.54
- MAE : train 131 183.57 vs test 170 018.55, écart = 38 834.98
- R2 : train 0.5307 vs test 0.4191, écart = 0.11
- MAPE : train 113.83 vs test 164.09, écart = 50.26

Conclusion :

- Le modèle généralise raisonnablement, mais reste sensible au bruit et à la structure hétérogène des prix.
- Le niveau de variance globale est encore trop élevé pour garantir une précision métier stable.

## 6. Analyse par segment

### 6.1 Par gouvernorat

Les segments les mieux maîtrisés sont :

- Ben Arous : MAE = 54 034.32 TND
- Sousse : MAE = 123 089.04 TND

Les segments les plus délicats sont :

- Tunis : MAE = 316 136.19 TND
- Autre : MAE = 263 646.28 TND
- Nabeul : MAE = 202 563.15 TND

Interprétation :

- La dispersion des prix est forte dans les zones urbaines très hétérogènes.
- Les gouvernorats présentant des marchés plus homogènes ou mieux couverts par les features se comportent mieux.

### 6.2 Par type de bien

Les types de bien avec les meilleures erreurs absolues sont :

- Appartement : MAE = 121 201.46 TND
- Duplex : MAE = 332 669.95 TND
- Terrain : MAE = 202 064.48 TND

Les types les plus difficiles :

- Villa : MAE = 398 064.22 TND
- Autre : MAE = 316 900.63 TND
- Maison : MAE = 203 736.94 TND

Interprétation :

- Les villas présentent une forte variabilité de prix, probablement liée à des caractéristiques non captées par les features actuelles.
- Les types de biens rares ou peu représentés restent difficiles à modéliser.

### 6.3 Par tranche de prix

- Q1 (bas prix) : MAE = 71 724.94
- Q2 : MAE = 80 474.70
- Q3 : MAE = 100 960.17
- Q4 (haut prix) : MAE = 433 030.44

Conclusion :

- Le modèle est relativement meilleur sur les tranches basses et intermédiaires.
- La prévision sur les biens très chers reste très instable, probablement en raison d’une queue de distribution très longue et d’un manque de qualité d’échantillonnage.

## 7. Analyse des visualisations

### 7.1 Comparaison des prédictions par rapport au benchmark Mubawab

La figure “Model Predictions vs Mubawab Benchmarks” montre que le modèle reproduit grossièrement les niveaux de prix observés dans le benchmark, mais l’écart reste visible sur plusieurs zones géographiques.

Conclusion :

- La direction de la prédiction est acceptable,
- mais l’alignement absolu avec le benchmark n’est pas encore suffisamment précis pour un usage industriel.

### 7.2 Graphiques de diagnostics du modèle

Les visualisations produites dans `visualizations/` mettent en évidence les points suivants :

1. `01_actual_vs_predicted.png`
   - Les prix réels et prédits sont globalement alignés en tendance.
   - La dispersion reste élevée, surtout sur les biens à valeur élevée.

2. `02_residual_distribution.png`
   - Les résidus sont centrés autour de zéro, mais avec une queue lourde à droite.
   - Le comportement est compatible avec une cible log-space très skewée.

3. `03_residual_vs_predicted.png`
   - Le modèle présente une structure hétéroscédastique : l’erreur augmente avec la valeur prédite.

4. `04_feature_importance.png`
   - Les features les plus influentes sont principalement des variables de localisation, de surface et de typologie de bien.
   - Les variables d’équipements ont un impact relatif limité, ce qui suggère un besoin à approfondir sur la qualité et le codage de ces features.

5. `05_learning_curves.png`
   - La courbe d’apprentissage montre que le modèle converge correctement.
   - L’écart entre train et validation reste présent mais relativement contrôlé.

6. `06_prediction_intervals.png`
   - Les intervalles de prédiction restent larges sur plusieurs zones.
   - Le modèle est donc utile pour la direction générale, mais pas encore pour une estimation très précise avec faible incertitude.

7. `11_cv_scores_boxplot.png`
   - Le LightGBM est le plus stable en validation croisée par rapport aux autres modèles testés.

8. `12_hyperparameter_sensitivity.png`
   - Les hyperparamètres les plus sensibles sont ceux liés au nombre de feuilles, à l’échantillonnage et à la profondeur.

9. `13_external_validation.png`
   - Le modèle répond bien en tendance, mais les objectifs de précision restent hors cible,
   - ce qui indique un potentiel d’amélioration dans l’ingénierie de features et/ou la calibration.

## 8. Conclusion globale sur la phase d’entraînement

### Points positifs

- Le pipeline de preprocessing est bien structuré et compatible avec un entraînement supervisé.
- Le `LightGBM` est clairement le meilleur modèle parmi les candidats évalués.
- Les visualisations montrent que le modèle capte bien la tendance générale des prix.
- Les artefacts `best_model.joblib` et `preprocessor.joblib` ont bien été générés et sont prêts pour une utilisation d’inférence.

### Points faibles

- Les performances absolues ne satisfont pas encore les seuils métier visés.
- Les erreurs restent significatives, en particulier sur les biens chers et sur certains gouvernorats.
- L’hétérogénéité du marché tunisien et le skew fort de la cible limitent la précision actuelle.

## 9. Recommandations pour la prochaine itération

1. Revoir l’ingénierie des features de localisation et de typologie.
2. Explorer un traitement plus robuste des outliers sur la queue haute des prix.
3. Tester un modèle de stacking ou une calibration post-training.
4. Ajouter des features métier plus discriminantes (quartier, proximité, ancien/neuf, état du bien, etc.).
5. Refaire l’évaluation sur un jeu plus homogène ou segmenté par marché.

## 10. Verdict final

La phase d’entraînement a réussi à produire un modèle fonctionnel et un pipeline de preprocessing robuste, avec un `LightGBM` comme meilleur candidat. Cependant, les performances obtenues restent insuffisantes pour un usage métier final strict sans améliorations supplémentaires.

Le projet est donc dans une phase de validation technique positive, mais pas encore dans une phase de validation métier complète.
