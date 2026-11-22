/* OpenBridge site: English is in the HTML; French lives here. Choice: ?lang=, then saved choice, then browser language. */
(function () {
  'use strict';
  var FR = {
    /* nav & footer */
    'nav.skip': 'Aller au contenu', 'nav.try': 'Essayer', 'nav.compat': 'Compatibilité', 'nav.bench': 'Benchmarks',
    'nav.partners': 'Partenaires', 'nav.cta': 'Devenir partenaire',
    'foot.by': 'OpenBridge, conçu par un développeur indépendant.', 'foot.start': 'Par où commencer',
    'foot.security': 'Sécurité', 'foot.privacy': 'Confidentialité', 'foot.licensing': 'Licences', 'foot.new': 'Nouveautés', 'foot.roadmap': 'Feuille de route',
    'foot.notrack': 'Code source consultable sous licence PolyForm Strict 1.0.0. Aucun traceur sur ce site. La vidéo ne se charge depuis YouTube que si vous appuyez sur lecture.',
    'lvl.real': 'Matériel réel', 'lvl.vm': 'Machines virtuelles', 'lvl.off': 'Émulateurs officiels', 'lvl.emu': 'Émulateur, matériel à venir', 'lvl.emuwait': 'Émulateur, lunettes en route',

    /* home */
    'home.title': 'OpenBridge : donnez à votre matériel des pouvoirs qu’il n’a jamais eus',
    'home.h1': 'Donnez à votre matériel des pouvoirs qu’il n’a jamais eus.',
    'home.sub': 'Brisez les murs entre vos appareils. Dites ce que vous voulez, ils s’organisent ensemble.',
    'home.cta.try': 'Essayer dans le navigateur', 'home.cta.demo': 'Voir la démo de 3 minutes',
    'home.trust': 'Rien ne s’exécute sans votre accord. Chaque action est vérifiée ensuite sur l’appareil réel. L’IA tourne sur votre propre machine.',
    'scene.tv': 'TV du salon', 'scene.robot': 'Robot aspirateur', 'scene.start': 'Démarrer', 'scene.pause': 'Pause', 'scene.dock': 'Base',
    'scene.created': 'Créé à la demande par OpenBridge', 'scene.say': '« Mets des boutons aspirateur sur la TV »',
    'scene.done': 'Aspirateur lancé : fait, vérifié', 'scene.read': 'Relu sur le robot : en nettoyage',
    'scene.aria': 'Une demande pour mettre des commandes d’aspirateur sur la TV : les boutons apparaissent sur la TV, on appuie sur Démarrer, le robot démarre, et un reçu confirme que c’est fait et vérifié.',
    'home.demo.h': 'De vrais appareils. Un vrai salon. Aucune maquette.',
    'home.demo.p': 'Chaque séquence a été filmée au téléphone, face au vrai matériel : une Android TV, une Galaxy Watch7, des téléphones Android et un robot aspirateur.',
    'home.demo.alt': 'Vidéo de démonstration d’OpenBridge', 'home.demo.play': 'Lancer la démo', 'home.demo.playaria': 'Lancer la démo OpenBridge de 3 minutes (charge YouTube)',
    'home.c1.h': '« Lance l’aspirateur », dit à la TV', 'home.c1.p': 'La TV reçoit des boutons d’aspirateur qu’elle n’a jamais eus. On appuie, le robot démarre.', 'home.c1.alt': 'Dire « lance l’aspirateur » à la TV démarre le robot aspirateur',
    'home.c2.h': 'Votre montre devient une télécommande TV', 'home.c2.p': 'On le demande à voix haute à la montre. Des boutons de volume y apparaissent, et ils pilotent la TV.', 'home.c2.alt': 'Demander à la montre des boutons de volume TV, puis les utiliser',
    'home.c3.h': 'Il sait dire non', 'home.c3.p': 'L’état de l’appareil n’est pas confirmé à jour ? OpenBridge refuse, et dit pourquoi.', 'home.c3.alt': 'OpenBridge refuse une action car l’état de l’appareil n’est plus à jour',
    'home.how.h': 'La couche qui manquait entre toutes vos marques.',
    'home.how.p': 'Chaque appareil vit dans sa propre appli, son propre cloud, sa propre télécommande. OpenBridge se place entre eux, apprend ce que chacun sait vraiment faire, et compose ce que vous demandez.',
    'home.s1.h': 'Découvrir', 'home.s1.p': 'Trouve les appareils autour de vous en Wi-Fi, USB, Bluetooth, ou via votre téléphone et votre TV.',
    'home.s2.h': 'Comprendre', 'home.s2.p': 'Apprend ce que chaque appareil sait faire de façon vérifiable, et ce qu’il a le droit de faire.',
    'home.s3.h': 'Créer', 'home.s3.p': 'Vous demandez en français ou en anglais. L’IA construit la commande qu’il vous faut, sur l’écran de votre choix.',
    'home.s4.h': 'Approuver et vérifier', 'home.s4.p': 'Vous approuvez, il agit, puis il relit l’appareil. Pas de confirmation, pas de « fait ».',
    'home.p1.h': 'Brisez les murs', 'home.p1.p': 'Toutes les marques, tous les écrans. TV, objets connectés portés, téléphones, box, robots et PC parlent enfin la même langue.',
    'home.p2.h': 'Débloquez de nouvelles fonctionnalités', 'home.p2.p': 'Des commandes, des alertes et des parcours vocaux que vos appareils n’avaient pas à l’achat, créés dès que vous les demandez.',
    'home.p3.h': 'Gardez le contrôle', 'home.p3.p': 'Rien ne s’exécute sans votre accord, chaque commande peut être retirée, et l’IA tourne en local, gratuitement.',
    'home.proof.h': 'Prouvé sur du vrai matériel, pas sur des slides.',
    'home.proof.p': 'Chaque résultat est consigné dans un registre de preuves public. Tout ce qui est émulé est signalé comme tel, et jamais compté comme preuve physique.',
    'home.f1': 'tests automatisés', 'home.f2': 'vérifications sur du matériel réel', 'home.f3': 'plateformes, un seul code', 'home.f4': 'dépendance à l’exécution',
    'home.t.dev': 'Appareil', 'home.t.what': 'Ce qu’OpenBridge en fait', 'home.t.proof': 'Preuve',
    'home.r1': 'Appli compagnon, panneaux de commande créés par l’IA, demandes vocales, volume et alimentation',
    'home.r2': 'Demandes vocales, commandes créées et retirées à la volée, pilote la TV',
    'home.r3d': 'Téléphones Android', 'home.r3': 'Compagnon, appairage, relais Bluetooth, actions sur l’appareil',
    'home.r4d': 'Robot aspirateur (Tuya)', 'home.r4': 'Démarrer, mettre en pause et renvoyer à la base depuis la TV ou le PC, avec relecture de l’état',
    'home.r5d': 'Box Freebox Delta', 'home.r5': 'Inventaire du réseau et découverte des appareils, en lecture seule par principe',
    'home.r6d': 'PC Windows', 'home.r6': 'Agent à distance entre PC, tâches soumises à consentement',
    'home.r7d': 'Lunettes connectées ENGO', 'home.r7': '38 fonctionnalités d’affichage tête haute, un émulateur professionnel, le pont avec l’appli officielle',
    'home.r8': 'Agent léger sur de vrais systèmes invités', 'home.r9': 'Agent natif pour microcontrôleur, émulateur Android',
    'home.proof.compat': 'Explorer toutes les vérifications', 'home.proof.bench': 'Voir les benchmarks',
    'home.pa.h': 'Vous fabriquez des appareils. Nous les faisons fonctionner avec tout le reste.',
    'home.pa.p': 'En devenant partenaire, votre produit cesse d’être une île : de nouvelles fonctionnalités sans nouveau firmware, l’interopérabilité avec les autres marques, et un banc de test qui ne dort jamais.',
    'home.pa.first': 'Notre premier partenaire matériel',
    'home.g1.h': 'De nouvelles fonctionnalités, sans nouveau firmware', 'home.g1.p': 'Commandes, alertes, voix et parcours multi-appareils, construits sur ce que votre appareil expose déjà.',
    'home.g2.h': 'Interopérabilité avec les autres marques', 'home.g2.p': 'Votre appareil fonctionne avec les TV, montres, téléphones, box, robots et PC d’autres fabricants, sous un même modèle de consentement et de vérification.',
    'home.g3.h': 'Des tests et benchmarks complets', 'home.g3.p': 'Des centaines de tests automatisés et des benchmarks sur le matériel réel pour votre produit, relancés à chaque changement, sur trois systèmes d’exploitation.',
    'home.g4.h': 'Une compatibilité élargie', 'home.g4.p': 'Joignable en USB, Wi-Fi, BLE ou via un appareil relais, sur six plateformes, même d’anciens Windows.',
    'home.g5.h': 'Un émulateur de votre appareil', 'home.g5.p': 'Un modèle logiciel fidèle pour vos développeurs, votre QA et vos démos commerciales, sans appareil sur le bureau.',
    'home.g6.h': 'Un rapport de compatibilité public et vérifié', 'home.g6.p': 'Chaque affirmation appuyée par une preuve, plus un retour détaillé sur votre API ou votre SDK.',
    'home.case.alt': 'HUD Studio émulant les lunettes ENGO', 'home.case.h': 'ENGO : livré avant même l’arrivée des lunettes',
    'home.case.1': 'fonctionnalités d’affichage tête haute, rendues et mesurées', 'home.case.2': 'tests automatisés dédiés, tous au vert',
    'home.case.3': 'documents techniques, du protocole BLE aux pièges du firmware', 'home.case.4': 'émulateur professionnel, piloté par l’appli officielle ActiveLook',
    'home.case.st': 'Validé dans l’émulateur. Les tests sur le matériel commencent à l’arrivée de la paire.', 'home.case.link': 'Lire l’étude de cas ENGO',
    'home.ask.h': 'Ce que nous demandons',
    'home.ask.p': '<strong>Du matériel à conserver :</strong> un don ou un prêt permanent, jamais un prêt limité dans le temps, pour que les tests et benchmarks tournent à chaque version. Plus la documentation de l’API ou du SDK et un contact technique.',
    'home.keep.h': 'Ce qui reste à vous',
    'home.keep.p': '<strong>Votre code et vos données.</strong> Les partenaires reçoivent une licence commerciale pour leur intégration, et nous travaillons volontiers sous votre NDA : rien de confidentiel n’arrive dans le dépôt public. Voir <a href="https://github.com/toskaman/openbridge/blob/main/docs/LICENSING.md#commercial--partner-licensing">licences</a>, <a href="https://github.com/toskaman/openbridge/blob/main/SECURITY.md">sécurité</a> et <a href="https://github.com/toskaman/openbridge/blob/main/docs/PRIVACY.md">confidentialité</a> (en anglais).',
    'home.road.h': 'La suite dépend du matériel sur le banc.', 'home.road.p': 'Un appareil partenaire passe directement en tête de liste.',
    'home.road.now': 'Maintenant', 'home.road.next': 'Ensuite', 'home.road.later': 'Plus tard',
    'home.road.n1': 'Lunettes ENGO sur le matériel réel', 'home.road.n2': 'Rapports de benchmarks publics par appareil', 'home.road.n3': 'Programme partenaires',
    'home.road.x4': 'Plus de TV, d’objets portés et de robots', 'home.road.l1': 'OpenBridge sans PC', 'home.road.l2': 'Bornes de recharge et mobilité', 'home.road.l3': 'Passerelles industrielles',
    'home.road.links': '<a href="https://github.com/toskaman/openbridge/blob/main/ROADMAP.md">Feuille de route complète</a> et <a href="https://github.com/toskaman/openbridge/blob/main/CHANGELOG.md">nouveautés</a> (en anglais).',
    'home.co.h': 'Donnons de nouveaux pouvoirs à vos appareils.', 'home.co.p': 'Parlez-nous de votre produit. Réponse en français ou en anglais.',
    'home.co.pdf': 'Télécharger la plaquette partenaire (PDF, en anglais)', 'home.co.req': 'Publier une demande de partenariat', 'home.co.gh': 'Voir le code sur GitHub', 'home.co.dl': 'Télécharger pour Windows',
    'home.r10d': 'Pont Home Assistant', 'home.r10': 'Lumières, prises, thermostats, volets, serrures et robots connus de Home Assistant, Matter compris', 'lvl.simapi': 'API simulée, test réel à venir',

    /* try */
    'try.title': 'Essayer OpenBridge dans le navigateur (simulation)',
    'try.h1': 'Essayez OpenBridge dans votre navigateur.',
    'try.p': 'Demandez quelque chose à trois appareils. OpenBridge propose un plan, attend votre accord, crée les boutons, puis relit l’appareil avant de dire « fait ».',
    'try.label': '<b>Simulation.</b> Tout se passe dans votre navigateur : aucun vrai appareil, aucun modèle d’IA, aucun réseau. Quelques règles fixes remplacent l’IA. Le vrai OpenBridge fait la même chose sur du vrai matériel, comme le montre la <a href="./#demo">vidéo de démo</a>.',
    'try.ask': 'Demandez à OpenBridge', 'try.inputlabel': 'Votre demande', 'try.send': 'Envoyer',
    'try.stale': 'Simuler un état d’appareil périmé (pour voir un refus)', 'try.reset': 'Recommencer',
    'try.tvsmall': 'Commandes rapides créées par OpenBridge', 'try.status': 'État', 'try.battery': 'Batterie', 'try.lastread': 'Dernière lecture',
    'try.receipts': 'Reçus', 'try.real': 'Le voir sur du vrai matériel', 'try.install': 'Télécharger pour Windows',
    'sim.you': 'Vous',
    'sim.hello': 'J’ai trouvé 3 appareils à proximité : une <b>TV du salon</b>, une <b>montre Galaxy</b> et un <b>robot aspirateur</b>. Que doivent-ils faire ensemble ?',
    'sim.dev.tv': 'TV du salon', 'sim.dev.watch': 'Montre Galaxy', 'sim.dev.robot': 'Robot aspirateur',
    'sim.plan.intro': 'Voici mon plan. Rien ne se passe sans votre accord.',
    'sim.plan.add': 'Ajouter {n} boutons sur la {screen} : {names}', 'sim.plan.drive': 'Ils commanderont uniquement cet appareil : {target}.',
    'sim.plan.check': 'Après chaque appui, je relis l’appareil avant de dire « fait ».',
    'sim.approve': 'Approuver', 'sim.decline': 'Refuser', 'sim.approved': 'Approuvé.', 'sim.declined': 'Refusé. Rien n’a été modifié.',
    'sim.act.intro': 'Je peux le faire : {action}. Vous approuvez ?',
    'sim.installed': 'Fait, vérifié : la {screen} affiche les nouveaux boutons. Essayez d’en appuyer un.',
    'sim.revoked': 'Retirés. Vérifié : plus aucun bouton OpenBridge sur aucun appareil, et les anciens appuis sont désormais refusés.',
    'sim.nothing': 'Il n’y a aucun bouton OpenBridge à retirer pour le moment.',
    'sim.policy': '<b>Refusé.</b> Les réglages de la box sont en lecture seule par principe : OpenBridge peut lister ce qui est sur votre réseau, mais ne modifie jamais la box. Rien n’a été envoyé.',
    'sim.unknown': '<b>Je ne peux pas.</b> Aucun appareil de ce type parmi les 3 que j’ai découverts, et OpenBridge n’agit jamais sur un appareil qu’il n’a pas trouvé et vérifié.',
    'sim.status': 'Robot aspirateur : <b>{st}</b>, batterie {b} %. Lu à l’instant sur le robot ; rien n’a été modifié.',
    'sim.stale': '<b>Refusé.</b> L’état du robot n’a pas été confirmé récemment, donc je n’agis pas. Rien n’a été envoyé. Désactivez « état périmé » et réessayez.',
    'sim.unclear': 'Je ne suis pas sûr de comprendre. Dans cette simulation, je comprends des demandes comme les suggestions ci-dessus.',
    'sim.a.start': 'démarrer le robot aspirateur', 'sim.a.pause': 'mettre le robot aspirateur en pause', 'sim.a.dock': 'renvoyer le robot aspirateur à sa base',
    'sim.a.volup': 'monter le volume de la TV', 'sim.a.voldown': 'baisser le volume de la TV',
    'sim.ctrl.start': 'Démarrer', 'sim.ctrl.pause': 'Pause', 'sim.ctrl.dock': 'Base', 'sim.ctrl.volup': 'Volume +', 'sim.ctrl.voldown': 'Volume −',
    'sim.st.docked': 'Sur sa base, en charge', 'sim.st.cleaning': 'En nettoyage', 'sim.st.paused': 'En pause', 'sim.st.returning': 'Retour à la base',
    'sim.s1': 'Mets des boutons aspirateur sur la TV', 'sim.s2': 'Transforme ma montre en télécommande TV', 'sim.s3': 'Renvoie le robot à sa base',
    'sim.s4': 'Enlève les boutons', 'sim.s5': 'Change le mot de passe Wi-Fi de ma box', 'sim.s6': 'Déverrouille la porte d’entrée',
    'sim.noctrl': 'Pas encore de boutons OpenBridge', 'sim.noctrlw': 'Pas encore de boutons', 'sim.volume': 'Volume',
    'sim.fresh': 'Confirmée à l’instant', 'sim.notfresh': 'Non confirmée récemment',
    'sim.norc': 'Les reçus s’affichent ici : ce qui a été demandé, approuvé, fait et vérifié.',
    'sim.rc.refused': 'Refusé : {x}', 'sim.rc.stale': 'État de l’appareil non confirmé récemment. Rien n’a été envoyé.',
    'sim.rc.revoked': 'Boutons retirés partout', 'sim.rc.revokedd': 'Vérifié : 0 bouton OpenBridge restant sur la TV et la montre.',
    'sim.rc.read': 'Lecture du robot aspirateur', 'sim.rc.readd': 'Lecture seule. Rien n’a été modifié.',
    'sim.x.router': 'modifier les réglages de la box', 'sim.rc.policy': 'Bloqué par principe. Rien n’a été envoyé.',
    'sim.rc.install': 'Installation des boutons sur la {x}', 'sim.rc.wait': 'Envoyé. Relecture de l’appareil…',
    'sim.rc.installed': 'Boutons installés sur la {x}', 'sim.rc.installedd': 'Fait, vérifié : l’écran indique {x} boutons.',
    'sim.rc.doing': '{x}', 'sim.rc.verified': 'Fait, vérifié. Relu sur l’appareil : {x}',

    /* compatibility */
    'compat.title': 'Compatibilité appareil par appareil : OpenBridge',
    'compat.h1': 'La compatibilité, appareil par appareil.',
    'compat.p': 'Chaque entrée vient du registre de preuves public : ce qui a été testé, sur quel appareil, comment c’est vérifié de façon indépendante, et ses limites connues. Matériel réel, machines virtuelles et émulateurs sont toujours distingués.',
    'compat.raw': 'Les relevés de test sont affichés tels qu’ils ont été consignés, en anglais.',
    'compat.catlabel': 'Catégorie d’appareil', 'compat.lvllabel': 'Niveau de preuve', 'compat.search': 'Chercher un appareil ou une action',
    'compat.all': 'Tous les appareils', 'compat.anyproof': 'Tout niveau de preuve',
    'compat.cat.screens': 'TV et écrans', 'compat.cat.wearables': 'Objets portés', 'compat.cat.phones': 'Téléphones', 'compat.cat.robots': 'Robots',
    'compat.cat.network': 'Réseau', 'compat.cat.pcs': 'PC', 'compat.cat.cross': 'Scénarios multi-appareils', 'compat.cat.glasses': 'Lunettes connectées',
    'compat.cat.vms': 'Machines virtuelles', 'compat.cat.micro': 'Microcontrôleurs',
    'compat.int.companion': 'Appli compagnon OpenBridge sur l’appareil', 'compat.int.adapter': 'Adaptateur sur le PC, via l’interface de l’appareil', 'compat.int.agent': 'Agent OpenBridge léger',
    'compat.run1': '1 vérification', 'compat.runs': '{n} vérifications', 'compat.last': 'dernière le', 'compat.pending': 'Tests matériels à l’arrivée de la paire',
    'compat.engo': '38 fonctionnalités d’affichage tête haute et 82 tests, validés dans l’émulateur HUD Studio piloté par l’appli officielle ActiveLook. Les résultats d’émulateur ne comptent jamais comme preuve matérielle : cet appareil n’est donc pas encore dans le registre de preuves.',
    'compat.engolink': 'Lire l’étude de cas ENGO', 'compat.oracle': 'Vérification indépendante', 'compat.limits': 'Limites connues', 'compat.evidence': 'Preuves',
    'compat.showing': '{n} appareils affichés sur {total}, appuyés par {runs} vérifications.', 'compat.none': 'Aucun appareil ne correspond à ces filtres.',
    'compat.err': 'La liste des appareils n’a pas pu être chargée. Elle est aussi dans le dépôt : docs/HARDWARE_TEST_MATRIX.md.',

    /* benchmarks */
    'bench.title': 'Benchmarks : OpenBridge',
    'bench.h1': 'Benchmarks, résultats défavorables compris.',
    'bench.p': 'Mesurés sur le matériel du projet et publiés dans le dépôt avec les commandes pour les relancer. Les essais synthétiques et simulés sont signalés comme tels.',
    'bench.t1': 'tests automatisés', 'bench.t1s': 'lancés sous Linux, Windows et macOS à chaque changement',
    'bench.t2': 'propositions dangereuses de l’IA refusées', 'bench.t2s': 'par le garde-fou, quelle que soit l’IA utilisée',
    'bench.t3': 'plantage sur 1 000 tours scriptés', 'bench.t3s': 'et aucun envoi non approuvé, aucun reçu inventé',
    'bench.t4': 'thread ou socket non libéré', 'bench.t4s': 'après 360 cycles d’une longue session',
    'bench.table': 'Afficher les données en tableau', 'bench.rules': 'Règles seules', 'bench.local': '(local)', 'bench.source': 'Source',
    'bench.c1.h': 'Décisions correctes, par voie d’IA',
    'bench.c1.p': 'Les mêmes 30 cas de planification, 3 répétitions chacun. Sur cette tâche étroite, une règle écrite à la main est aussi précise ; les modèles apportent une explication fondée sur les faits. Les résultats défavorables aux modèles sont conservés exprès.',
    'bench.c1.tip': 'correct, {v} % au bon format, {n} essais',
    'bench.route': 'Voie', 'bench.correct': 'Correct', 'bench.valid': 'Format valide', 'bench.attempts': 'Essais',
    'bench.synth': 'Entrées synthétiques, modèles locaux, 0 $.',
    'bench.c2.h': 'Propositions dangereuses, toutes refusées par le garde-fou',
    'bench.c2.p': 'Un cas sur cinq cache une cible dangereuse (interface système, messagerie). Quoi que propose l’IA, le garde-fou déterministe refuse : 100 % de refus pour chaque voie.',
    'bench.c2.of': 'proposées, toutes refusées', 'bench.c2.tip': 'propositions dangereuses sur {n} essais, {p} % refusées',
    'bench.unsafe': 'Propositions dangereuses', 'bench.refused': 'Refusées',
    'bench.c3.h': 'Temps médian pour obtenir un plan',
    'bench.c3.p': 'Sur un PC de bureau : Llama sur le processeur, Glimmer sur une RTX 4060 Ti. La règle répond en moins d’une milliseconde.',
    'bench.c3.instant': 'moins d’1 ms', 'bench.median': 'Médiane',
    'bench.c4.h': 'Latence des commandes sur une longue session',
    'bench.c4.p': '360 cycles de découverte, appairage, envoi et révocation en {d} s, avec des pannes injectées. Le maximum correspond à une commande en attente derrière un exercice de ré-appairage volontaire.',
    'bench.max': 'max', 'bench.measure': 'Mesure', 'bench.value': 'Valeur', 'bench.err': 'Taux d’erreur (pannes injectées uniquement)', 'bench.shutdown': 'Arrêt propre',
    'bench.sim': 'Réseau simulé, vrai code OpenBridge. Windows, Python 3.14.4.',
    'bench.c5.h': 'Vérifications, par niveau de preuve',
    'bench.c5.p': 'Chaque vérification a passé un contrôle indépendant sur l’appareil lui-même. Les résultats émulés sont comptés à part, et jamais comme preuve matérielle.',
    'bench.level': 'Niveau de preuve', 'bench.runs': 'Vérifications', 'bench.c5.link': 'Voir chaque vérification sur la page Compatibilité',
    'bench.c6.h': 'Zéro défaillance grave sur 1 000 tours scriptés',
    'bench.c6.p': '200 conversations, 1 000 tours, lancés sur la base de règles. Cet essai mesure la sécurité, pas la couverture : la plupart des demandes reçoivent « non pris en charge », ce qui est la réponse honnête pour cette base.',
    'bench.c6.crash': 'Plantages', 'bench.c6.send': 'Envois externes non approuvés', 'bench.c6.fake': 'Reçus inventés', 'bench.c6.unk': 'Actions inconnues proposées',
    'bench.count': 'Nombre', 'num.tests': '2\u202f400+', 'bench.err2': 'Les données de benchmark n’ont pas pu être chargées. Elles sont aussi dans le dépôt : docs/benchmark/.'
  };

  var KEY = 'ob-lang';
  function pick() {
    var q = new URLSearchParams(location.search).get('lang');
    if (q === 'fr' || q === 'en') return q;
    try { var s = localStorage.getItem(KEY); if (s === 'fr' || s === 'en') return s; } catch (e) {}
    return (navigator.language || '').toLowerCase().indexOf('fr') === 0 ? 'fr' : 'en';
  }
  window.OB_LANG = 'en';
  window.obT = function (k, en) { return (window.OB_LANG === 'fr' && FR[k]) || en; };

  function apply(lang) {
    window.OB_LANG = lang;
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      if (el.dataset.en == null) el.dataset.en = el.innerHTML;
      var k = el.getAttribute('data-i18n');
      el.innerHTML = (lang === 'fr' && FR[k]) ? FR[k] : el.dataset.en;
    });
    document.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      el.getAttribute('data-i18n-attr').split(';').forEach(function (pair) {
        var p = pair.split(':'), attr = p[0].trim(), k = (p[1] || '').trim(), store = 'en' + attr.replace(/[^a-z]/gi, '');
        if (el.dataset[store] == null) el.dataset[store] = el.getAttribute(attr) || '';
        el.setAttribute(attr, (lang === 'fr' && FR[k]) ? FR[k] : el.dataset[store]);
      });
    });
    document.querySelectorAll('[data-lang-toggle]').forEach(function (b) {
      b.innerHTML = lang === 'fr' ? 'EN / <b>FR</b>' : '<b>EN</b> / FR';
      b.setAttribute('aria-label', lang === 'fr' ? 'Switch to English' : 'Passer en français');
    });
    var page = document.body.getAttribute('data-page');
    document.querySelectorAll('.nav [data-page]').forEach(function (a) { if (a.getAttribute('data-page') === page) a.setAttribute('aria-current', 'page'); });
    document.dispatchEvent(new CustomEvent('ob:lang', { detail: lang }));
  }

  function init() {
    apply(pick());
    document.addEventListener('click', function (e) {
      var b = e.target.closest('[data-lang-toggle]'); if (!b) return;
      var next = window.OB_LANG === 'fr' ? 'en' : 'fr';
      try { localStorage.setItem(KEY, next); } catch (err) {}
      apply(next);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
