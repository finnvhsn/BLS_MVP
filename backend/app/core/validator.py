"""Plan-Validierung gegen den Regelkatalog (F_OM_012, F_OM_015, NF_010).

Nutzt ausschließlich die Regeln aus rules.py — keine eigene Regel-Logik.
"""

from __future__ import annotations

from .plan import Plan, PlanKontext, PlanZuweisung
from .rules import HARTE_REGELN, Konflikt


def plan_validieren(plan: Plan, kontext: PlanKontext) -> list[Konflikt]:
    """Vollständige Prüfung aller harten Regeln H1–H9. Reihenfolge = Katalog."""
    konflikte: list[Konflikt] = []
    for regel in HARTE_REGELN.values():
        konflikte.extend(regel.pruefen(plan, kontext))
    return konflikte


def aenderung_validieren(
    plan: Plan,
    kontext: PlanKontext,
    index: int,
    neue_zuweisung: PlanZuweisung,
) -> list[Konflikt]:
    """Live-Validierung einer manuellen Änderung (F_OM_012/F_OM_016):
    Was-wäre-wenn-Prüfung — der Plan wird nicht verändert.

    Liefert alle Konflikte des geänderten Plans, die die geänderte Zuweisung
    oder ihre Beteiligten betreffen (die Umbuchung kann auch andernorts
    bestehende Konflikte erzeugen, z. B. eine Doppelbegegnung am anderen Tag).
    """
    geaendert = plan.ersetzt(index, neue_zuweisung)
    beteiligte_bewerber = set(neue_zuweisung.bewerber_ids) | set(plan.zuweisungen[index].bewerber_ids)
    beteiligte_pruefer = set(neue_zuweisung.pruefer_ids) | set(plan.zuweisungen[index].pruefer_ids)
    relevant = []
    for konflikt in plan_validieren(geaendert, kontext):
        if (
            index in konflikt.zuweisungen
            or beteiligte_bewerber & set(konflikt.bewerber_ids)
            or beteiligte_pruefer & set(konflikt.pruefer_ids)
        ):
            relevant.append(konflikt)
    return relevant
