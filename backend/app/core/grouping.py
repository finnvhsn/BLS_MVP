"""Stufe 1 des Solvers: Gruppeneinteilung der Bewerbenden (F_OM_006, W3).

Zufallsbasiert (Seed ⇒ reproduzierbar) mit anschließender lokaler Verbesserung
des Diversitäts-Scores (Geschlecht, Studiengang). Eigenständig wiederholbar
und manuell nachjustierbar — unabhängig von Stufe 2 (CP-SAT).
"""

from __future__ import annotations

import random
from dataclasses import replace

from ..db.models import Tag
from .plan import GruppeInfo, PlanKontext
from .rules import w3_diversitaet_gruppe


def gruppen_einteilen(
    kontext: PlanKontext, seed: int, verbesserungs_runden: int = 2000
) -> dict[Tag, list[list[int]]]:
    """Teilt die planbaren Bewerbenden je Tag in Gruppen konfigurierter Größe.

    Rückgabe: je Tag eine Liste von Gruppen (Listen von Bewerber-IDs).
    Bei nicht aufgehender Teilung sind einzelne Gruppen um 1 kleiner
    (Szenario 2: Gruppenarbeiten mit reduzierter Größe durchführbar).
    """
    rnd = random.Random(seed)
    groesse = kontext.konfiguration.gruppengroesse
    ergebnis: dict[Tag, list[list[int]]] = {}

    for tag in (Tag.FR, Tag.SA):
        ids = sorted(b.id for b in kontext.planbare_bewerber(tag))
        if not ids:
            ergebnis[tag] = []
            continue
        rnd.shuffle(ids)

        # Anzahl Gruppen so, dass keine Gruppe größer als `groesse` ist;
        # Rest wird gleichmäßig verteilt (Gruppen mit groesse-1 statt Mini-Gruppe).
        anzahl_gruppen = -(-len(ids) // groesse)  # ceil
        gruppen: list[list[int]] = [[] for _ in range(anzahl_gruppen)]
        for i, bid in enumerate(ids):
            gruppen[i % anzahl_gruppen].append(bid)

        _diversitaet_verbessern(gruppen, kontext, rnd, verbesserungs_runden)
        ergebnis[tag] = gruppen

    return ergebnis


def _diversitaet_verbessern(
    gruppen: list[list[int]], kontext: PlanKontext, rnd: random.Random, runden: int
) -> None:
    """Hill-Climbing: zufällige Paar-Tausche zwischen Gruppen, akzeptiert wenn
    der Gesamt-Diversitäts-Score (W3) steigt."""
    if len(gruppen) < 2:
        return

    def score(g: list[int]) -> float:
        return w3_diversitaet_gruppe(g, kontext)

    for _ in range(runden):
        gi, gj = rnd.sample(range(len(gruppen)), 2)
        a = rnd.randrange(len(gruppen[gi]))
        b = rnd.randrange(len(gruppen[gj]))
        vorher = score(gruppen[gi]) + score(gruppen[gj])
        gruppen[gi][a], gruppen[gj][b] = gruppen[gj][b], gruppen[gi][a]
        if score(gruppen[gi]) + score(gruppen[gj]) < vorher:
            gruppen[gi][a], gruppen[gj][b] = gruppen[gj][b], gruppen[gi][a]  # rückgängig


def gruppen_auffuellen(kontext: PlanKontext) -> PlanKontext:
    """Ordnet planbare Bewerbende ohne Gruppe (Nachrücker, Szenario 3) der
    kleinsten Gruppe ihres Tages zu; sind alle Gruppen voll, entsteht eine neue.
    Bestehende Gruppen bleiben unangetastet (W6: minimalinvasiv)."""
    groesse = kontext.konfiguration.gruppengroesse
    bewerber = dict(kontext.bewerber)
    gruppen = dict(kontext.gruppen)

    belegung: dict[int, int] = {g.id: 0 for g in gruppen.values()}
    for b in bewerber.values():
        if b.planbar and b.gruppe_id in belegung:
            belegung[b.gruppe_id] += 1

    for bid in sorted(b.id for b in bewerber.values() if b.planbar and b.gruppe_id is None):
        info = bewerber[bid]
        kandidaten = sorted(
            (g for g in gruppen.values()
             if g.tag == info.tag and belegung[g.id] < groesse),
            key=lambda g: (belegung[g.id], g.nummer),
        )
        if kandidaten:
            ziel = kandidaten[0]
        else:
            naechste_id = max(gruppen, default=0) + 1
            naechste_nummer = max(
                (g.nummer for g in gruppen.values() if g.tag == info.tag), default=0
            ) + 1
            ziel = GruppeInfo(id=naechste_id, tag=info.tag, nummer=naechste_nummer)
            gruppen[ziel.id] = ziel
            belegung[ziel.id] = 0
        bewerber[bid] = replace(info, gruppe_id=ziel.id)
        belegung[ziel.id] += 1

    return replace(kontext, bewerber=bewerber, gruppen=gruppen)


def kontext_mit_gruppen(
    kontext: PlanKontext, einteilung: dict[Tag, list[list[int]]]
) -> PlanKontext:
    """Erzeugt einen neuen Kontext, in dem GruppeInfo-Objekte angelegt und die
    Bewerbenden zugeordnet sind (pure — DB-Persistenz erfolgt in der API-Schicht)."""
    gruppen: dict[int, GruppeInfo] = {}
    zuordnung: dict[int, int] = {}
    naechste_id = 1
    for tag in (Tag.FR, Tag.SA):
        for nummer, mitglieder in enumerate(einteilung.get(tag, []), start=1):
            gruppe = GruppeInfo(id=naechste_id, tag=tag, nummer=nummer)
            gruppen[gruppe.id] = gruppe
            for bid in mitglieder:
                zuordnung[bid] = gruppe.id
            naechste_id += 1

    bewerber = {
        bid: (replace(info, gruppe_id=zuordnung[bid]) if bid in zuordnung else info)
        for bid, info in kontext.bewerber.items()
    }
    return replace(kontext, bewerber=bewerber, gruppen=gruppen)
