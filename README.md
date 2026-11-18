# Arcade · Mon cahier de code (CP · CE1)

Cahier d'activités numérique pour apprendre à coder aux enfants de **CP et de CE1** et développer leur **logique algorithmique**,
avec le Professeur Pile Poil, le savant venu de la planète des Savants.

Le parcours compte **30 séances**, à faire dans l'ordre, sur tablette (une tablette par enfant).
Chaque séance est une petite aventure : une histoire, des devinettes, des défis, et un programme à écrire.
La séance se valide automatiquement à la fin et ouvre la suivante. Les points s'additionnent dans le cahier.

## Les séances

| N° | Séance | Notion |
|---|---|---|
| 1 | **Le voyage du Professeur Pile Poil** : trouver le bug de la fusée, réussir 3 défis, programmer le voyage jusqu'à la Terre | Algorithme : des instructions dans le bon ordre (directions) |
| 2 → 30 | Bientôt | |

## Organisation des fichiers

```
index.html            ← le cahier d'activités (page d'accueil)
seance-1/
  index.html          ← la séance 1
  texts.json          ← textes modifiés de la séance
  audio/              ← voix du Professeur (<id>.mp3)
seance-2/ …           ← les séances suivantes, sur le même modèle
```

## Ajouter une séance

1. Créer le dossier `seance-N/` avec son `index.html`.
2. Dans le `index.html` de la racine, remplir la séance dans la liste `SEANCES` (titre, url, clé de sauvegarde, résumé, mot du jour, étapes).
3. Dans la séance, mettre `SEANCE_N = N` : à la fin de la séance, elle se valide dans le cahier.

## Fonctionnement

- Pages HTML autonomes, déployées sur Vercel depuis GitHub.
- La progression est enregistrée sur la tablette (stockage du navigateur).
- Menu intervenant (⚙ dans le cahier) : « Nouvel enfant » efface la progression de toutes les séances.
- Dans une séance : phrases du Professeur lues à voix haute, avec une consigne courte écrite dans la bulle.
  Les textes se modifient dans l'écran « Modifier les textes » ou dans `texts.json`.
