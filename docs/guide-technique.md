# Pro Micro Key — guide technique

Ce guide détaille la web app, le firmware et le dépannage USB. Pour comprendre le montage complet avec les deux relais Smart Life/Tuya, commencer par le [README principal](../README.md).

Web app Python locale, en français, pour flasher un **Pro Micro ATmega32U4** et configurer la saisie d’un mot de passe au branchement USB, à l’appui d’un bouton, ou les deux. Interface inspirée du thème [Spotlight](https://bootstrapmade.com/demo/Spotlight/) : fond anthracite, navigation arrondie, surfaces sobres et accent **#0076ff**. Les polices Roboto, Raleway et Poppins sont intégrées localement avec leurs licences libres.

Le **switch clair/sombre** dans l’en-tête change le thème et mémorise uniquement cette préférence dans le navigateur. Le mode sombre est utilisé au premier lancement.

Le schéma interactif utilise le **SVG Pro Micro fourni**, conservé dans `static/images/pro-micro.svg`. Ses 24 pastilles restent alignées avec les zones de sélection ; la broche choisie s’illumine en bleu, et l’aide RESET repère RST et GND en orange.

Compatible avec les deux variantes : **5 V / 16 MHz** et **3,3 V / 8 MHz**. Les Pro Micro RP2040 et les autres microcontrôleurs ne sont pas pris en charge.

## Démarrer

Prérequis : Linux ou macOS, Python 3.10 ou plus récent avec `venv`, `make`, un câble USB de données. Internet est nécessaire à l’installation des dépendances et des outils Arduino ; ensuite le fonctionnement est local.

```sh
make run
```

Ouvrir **http://127.0.0.1:5000**. Le serveur tourne en arrière-plan, uniquement sur l’interface locale.

```sh
make stop
make status
```

Pour un autre port : `make run PORT=5050`. Arrêter le serveur existant avant de changer de port. Le journal serveur est dans `.runtime/server.log` ; `make stop` n’arrête que le processus de ce projet. Une opération Arduino déjà lancée se termine avant la fermeture du processus.

## Première utilisation

1. Brancher la carte et vérifier le port USB dans la barre de connexion.
2. Ouvrir l’onglet **Installer**, puis cliquer sur **Installer les outils** si nécessaire, ou lancer `make tools`. Arduino CLI, les plateformes Arduino AVR et SparkFun AVR, et Keyboard sont installés dans `.tools/`. Le téléchargement d’Arduino CLI est vérifié par SHA-256.
3. Choisir la variante physique : **5 V / 16 MHz** ou **3,3 V / 8 MHz**. Les identités USB standards sont reconnues pour suggérer le profil et bloquer un choix incohérent. Vérifier aussi l’inscription sur la carte.
4. Cliquer sur **Flasher le firmware**. Cela remplace le programme actuel. Le nouveau firmware ne contient aucun mot de passe par défaut. Un ancien mot de passe de Pro Micro Key est conservé, y compris lors de la migration depuis le firmware 1.0.
5. Dans **Configurer**, choisir **Au branchement**, **Avec un bouton** ou **Les deux**. Pour un bouton, sélectionner la broche dans le menu ou directement sur le schéma : sa pastille s’illumine et le câblage s’affiche.
6. Saisir le mot de passe et choisir le clavier de l’ordinateur cible (**AZERTY français classique PC**, ou **QWERTY US**). Le délai s’applique au branchement ; un bouton déclenche immédiatement après filtrage des rebonds. L’intervalle entre touches et l’ajout d’Entrée sont dans **Options de saisie**.
7. Cliquer sur **Enregistrer sur la carte**. Les réglages sont conservés en EEPROM. Pour modifier les réglages ensuite, cliquer sur **Connecter**, laisser le mot de passe vide pour le conserver, puis enregistrer. Aucun nouveau flash n’est nécessaire après installation du firmware 1.1.
8. Débrancher la carte, ouvrir **Tester**, placer le curseur dans le champ, puis rebrancher. En mode bouton, appuyer sur le bouton pour déclencher. La carte fonctionne aussi lorsque la web app est fermée.

L’onglet **Tester** fournit un champ masqué qui n’envoie rien au serveur. Le test ne déclenche pas lui-même le clavier : utiliser le rebranchement ou le bouton, selon le mode choisi. Le firmware n’envoie aucun raccourci clavier et ne cherche pas automatiquement un champ de mot de passe.

## Brancher le bouton

Relier un bouton poussoir **normalement ouvert** entre la broche choisie et une broche **GND**. Le bouton doit fermer ce contact vers GND, sans alimentation externe.

```text
D4 (ou la broche choisie) ─── bouton poussoir ─── GND
```

Le firmware active `INPUT_PULLUP`, donc aucune résistance externe n’est nécessaire. Le schéma montre le Pro Micro vu de dessus, connecteur USB en haut ; vérifier les inscriptions du modèle physique avant le câblage. RAW, VCC, GND et RST ne sont pas des broches de déclenchement sélectionnables.

Les 18 entrées disponibles sont D0–D10, D14–D16 et A0–A3 (numéros Arduino 18–21). Le filtrage des rebonds est de 35 ms. Un appui produit une seule saisie, même si le bouton reste maintenu ; il faut relâcher avant un nouvel appui. Un bouton maintenu pendant le branchement ne déclenche pas le mode bouton : le relâcher puis appuyer.

## Générer un mot de passe

Le bouton **Générer**, sous le champ du mot de passe, propose une longueur de 8 à 128 caractères, avec 20 par défaut. La case **Compatible AZERTY + QWERTY**, cochée par défaut, limite la génération aux caractères saisis à l’identique sur AZERTY français classique PC et QWERTY US, sans changer le réglage clavier de la carte.

En mode compatible, les chiffres et les lettres A/Q/W/Z/M (minuscules et majuscules) sont exclus, car leurs touches ou modificateurs diffèrent. Si **Symboles** est coché, seuls **+ et =** sont ajoutés ; sinon, seules des lettres sont générées. Le résultat contient au moins une minuscule, une majuscule et, si demandé, un symbole. Cette sélection est vérifiée contre les tables [Arduino Keyboard FR](https://github.com/arduino-libraries/Keyboard/blob/1.0.6/src/KeyboardLayout_fr_FR.cpp) et [US](https://github.com/arduino-libraries/Keyboard/blob/1.0.6/src/KeyboardLayout_en_US.cpp). Elle ne couvre pas les variantes AFNOR, belge, suisse ou Mac.

En décochant **Compatible AZERTY + QWERTY**, la génération utilise minuscules, majuscules et chiffres, avec `!@#$%&*+-=?` si **Symboles** est coché. Dans ce mode, le **clavier de l’ordinateur** choisi doit correspondre à celui de la machine cible. L’option **Symboles** peut être désactivée si le service cible n’accepte que les lettres et chiffres.

La génération se fait entièrement dans le navigateur avec `crypto.getRandomValues`, sans appel réseau et sans enregistrement automatique. Les deux modes évitent accents, espaces, touches mortes et caractères ambigus (`0`, `O`, `1`, `I`, `l`). Les options s’appliquent au prochain clic sur **Générer** ; elles ne transforment pas un mot de passe déjà saisi ou enregistré. Les exigences du service cible, par exemple un chiffre obligatoire, restent à vérifier : le mode compatible ne produit aucun chiffre.

Le résultat remplit le champ masqué. Cliquer sur **Enregistrer sur la carte** pour l’appliquer ; générer seul ne change pas le mot de passe enregistré.

Le bouton **Copier**, à côté de **Voir**, copie le contenu du champ dans le presse-papiers sans l’afficher ni l’envoyer au serveur. Il est désactivé lorsque le champ est vide, et une confirmation apparaît après la copie. Il copie seulement le mot de passe saisi ou généré dans cette page : celui déjà stocké dans la carte ne peut pas être relu.

## Mot de passe et mémoire

- De 1 à 128 caractères ASCII imprimables, espaces compris. Les accents, caractères Unicode, sauts de ligne et tabulations sont refusés ; les espaces de début/fin sont conservés.
- La disposition choisie doit correspondre à celle active sur l’ordinateur cible. Les variantes AFNOR, belge, suisse et Mac ne sont pas équivalentes à l’AZERTY français PC. Vérifier les symboles sur la machine cible avant de l’utiliser pour une connexion ; les touches mortes peuvent dépendre de la disposition du système. Désactiver Verr. Maj. et ne pas maintenir de touche modificatrice pendant la saisie.
- Le mot de passe est stocké **en clair dans l’EEPROM de la carte** pour permettre la saisie. Ce n’est pas un coffre-fort chiffré : toute personne possédant la carte peut la brancher pour obtenir la saisie du secret.
- L’application ne crée aucun fichier de mot de passe, ne l’enregistre pas dans le navigateur et ne l’insère pas dans le firmware compilé. Il transite temporairement en mémoire et sur le port série, sans chiffrement. Python ne garantit pas l’effacement immédiat des chaînes en mémoire.
- La lecture série expose uniquement la longueur et les paramètres, jamais le mot de passe. Les journaux n’affichent pas le contenu de la configuration.
- **Effacer le mot de passe de la carte** écrase la zone EEPROM utilisée. La carte ne tape ensuite plus rien.
- Une commande de configuration `PMK1` désactive les déclenchements USB et bouton jusqu’au prochain démarrage pour éviter une saisie pendant l’édition. Une simple ouverture du port série (par exemple une sonde du système) ne les désactive plus depuis le firmware **1.1.0**. Après connexion/configuration, débrancher/rebrancher pour réarmer.
- Un redémarrage matériel réarme aussi la saisie. Le firmware ne répète pas la saisie périodiquement et ne ressaisit pas après une simple sortie de veille sans redémarrage.

## Accès USB sous Linux

Si le port est absent, vérifier le câble de données et la détection système :

```sh
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM*
```

Si le port existe mais l’accès est refusé, vérifier son groupe avec `ls -l` et vos groupes avec `id`. Sur Debian/Ubuntu, il s’agit généralement de `dialout` :

```sh
sudo usermod -aG dialout "$USER"
```

Sur d’autres distributions, utiliser le groupe propriétaire du port, souvent `uucp`. **Fermer puis rouvrir complètement la session utilisateur** après l’ajout au groupe. Ne pas lancer la web app avec `sudo` et ne pas rendre le port accessible à tous.

Fermer le moniteur série Arduino et les autres programmes utilisant le port. ModemManager peut parfois interférer ; le vérifier si le port est occupé ou si la saisie est annulée au branchement.

Si le port disparaît ou le téléversement échoue : faire deux contacts rapides entre **RST et GND**, actualiser les ports, puis relancer le flash pendant la fenêtre du bootloader. Vérifier la variante de carte sélectionnée. Le changement de numéro de port après flash est pris en charge.

### Récupérer une carte après un flash à la mauvaise fréquence

Un programme compilé en 8 MHz sur une carte 16 MHz peut empêcher sa reconnaissance USB. Le bootloader reste accessible par RESET ; aucune reprogrammation des fusibles n’est nécessaire.

Dans l’onglet **Installer**, choisir la variante physique correcte, ouvrir **Carte non détectée après un flash ?**, puis cliquer sur **Récupérer via RESET**. Quand le journal affiche « Récupération prête », faire deux contacts rapides entre **RST et GND** (ou deux appuis rapides sur RESET), carte branchée. L’application attend le bootloader pendant 60 secondes, téléverse puis vérifie le firmware. Le mot de passe en EEPROM est conservé. Les profils USB standards connus sont vérifiés pour refuser une fréquence incohérente.

Le bouton **Afficher le repère RESET**, sous le schéma, illumine **RST et GND en orange** et affiche le geste à faire. Le repère s’affiche aussi quand on ouvre l’aide de récupération. Relâcher complètement le contact après les deux impulsions. Si le port reste figé malgré le RESET, débrancher/rebrancher le câble USB avant une nouvelle récupération.

La récupération existe aussi en terminal :

```sh
make recover BOARD=5v16
# Ou, uniquement pour une carte physique 3,3 V / 8 MHz :
make recover BOARD=3v8
```

Le modèle ARCELI USB-C [B0FPRCNC8N](https://www.amazon.fr/dp/B0FPRCNC8N) est indiqué **5 V / 16 MHz** par sa fiche produit : utiliser `BOARD=5v16` pour ce modèle.

## Développement et vérification

```sh
make test
```

Tests des validations, du protocole série, des mises à jour de paramètres sans relire le secret, des options HTML, de la récupération, des routes locales et du verrou USB. Avec `g++`, une simulation exécute le firmware : délai USB, modes bouton et combiné, anti-rebond, bouton maintenu, migration EEPROM, CRC et effacement. Les périphériques sont simulés ; ces tests ne flashent pas de carte.

Si Node.js est disponible, `make test` exécute aussi les tests du générateur : alphabet compatible, longueurs, groupes de caractères, génération avec/sans symboles et renouvellement des valeurs. Node.js n’est pas nécessaire pour lancer la web app.

Pour compiler réellement pour les deux variantes, après `make tools` :

```sh
.venv/bin/python -c 'import device; device.compile_firmware("5v16", print); device.compile_firmware("3v8", print)'
```

Le serveur refuse les origines externes, les noms d’hôte externes et les écritures sans jeton de session. Il n’expose ni API réseau publique, ni service cloud. Ne pas modifier l’écoute locale pour l’exposer sur le réseau.

Fichiers principaux : `app.py` (HTTP), `device.py` (USB/Arduino), `firmware/promicro_key/promicro_key.ino` (firmware), `scripts/service.py` (cycle de vie du serveur).

Références : [cartes SparkFun](https://github.com/sparkfun/Arduino_Boards), [Arduino CLI](https://docs.arduino.cc/arduino-cli/), [bibliothèque Keyboard](https://github.com/arduino-libraries/Keyboard).
