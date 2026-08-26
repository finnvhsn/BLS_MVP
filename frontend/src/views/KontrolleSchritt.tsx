import { useCallback, useEffect, useState } from "react";
import { get } from "../api";
import { Konfliktliste } from "../components/Konfliktliste";
import { Planungsraster } from "../components/Planungsraster";
import { UmbuchungsDialog } from "../components/UmbuchungsDialog";
import type { Konflikt, PlanAnsicht, PrueferZeile, ZuweisungAnsicht } from "../types";

/** Schritt 4 – Kontrolle: Planungsansicht (F_OM_014), Konfliktliste mit
 * Navigation (F_OM_015), manuelle Nachbearbeitung (F_OM_012/016). */
export function KontrolleSchritt({ jahrgangId }: { jahrgangId: number }) {
  const [plan, setPlan] = useState<PlanAnsicht | null>(null);
  const [pruefende, setPruefende] = useState<PrueferZeile[]>([]);
  const [tag, setTag] = useState<"Fr" | "Sa">("Fr");
  const [sicht, setSicht] = useState<"raeume" | "bewerbende" | "pruefende">("raeume");
  const [markiert, setMarkiert] = useState<Set<number>>(new Set());
  const [auswahl, setAuswahl] = useState<ZuweisungAnsicht | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const laden = useCallback(async () => {
    setFehler(null);
    try {
      const [p, pr] = await Promise.all([
        get<PlanAnsicht>(`/api/jahrgaenge/${jahrgangId}/plan`),
        get<PrueferZeile[]>(`/api/jahrgaenge/${jahrgangId}/pruefende`),
      ]);
      setPlan(p);
      setPruefende(pr);
    } catch (e) {
      setPlan(null);
      setFehler(e instanceof Error ? e.message : "Plan konnte nicht geladen werden.");
    }
  }, [jahrgangId]);

  useEffect(() => {
    laden();
  }, [laden]);

  if (fehler) {
    return (
      <>
        <h2>Schritt 4 – Kontrolle</h2>
        <div className="karte"><p>{fehler}</p></div>
      </>
    );
  }
  if (!plan) return null;

  const kz = plan.planungsstand.kennzahlen as Record<string, number | Record<string, number>>;
  const springen = (k: Konflikt) => {
    setMarkiert(new Set(k.zuweisungen));
    const erste = plan.zuweisungen.find((z) => k.zuweisungen.includes(z.id));
    if (erste) {
      if (erste.tag !== tag) setTag(erste.tag);
      window.setTimeout(() => {
        document
          .getElementById(`zuweisung-${erste.id}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
    }
  };

  const abweichler = Object.keys((kz.w1_abweichler as Record<string, number>) ?? {}).length;

  return (
    <>
      <h2>Schritt 4 – Kontrolle</h2>

      <div className="karte">
        <div className="kennzahlen">
          <div className="kennzahl">
            <b>v{plan.planungsstand.version}</b>
            <span>{plan.planungsstand.typ}</span>
          </div>
          <div className="kennzahl">
            <b>{plan.konflikte.length}</b>
            <span>Konflikte</span>
          </div>
          <div className="kennzahl">
            <b>{String(kz.w1_erfuellt ?? "–")}/{String(kz.anzahl_geplante_bewerber ?? "–")}</b>
            <span>8 Prüfende erreicht {abweichler > 0 ? `(${abweichler} Abweichler)` : ""}</span>
          </div>
          <div className="kennzahl">
            <b>{String(kz.w2_durchschnitt ?? "–")}</b>
            <span>Ø Bewerbende je Prüfer:in (min {String(kz.w2_min)}, max {String(kz.w2_max)})</span>
          </div>
          <div className="kennzahl">
            <b>{String(kz.w5_wartezeit_max_min ?? "–")} min</b>
            <span>Längste Wartezeit (Summe {String(kz.w5_wartezeit_summe_min)} min)</span>
          </div>
          <div className="kennzahl">
            <b>{Math.round(((kz.w4_gemischte_pruefergruppen as number) ?? 0) * 100)}%</b>
            <span>Gemischte Prüfergruppen</span>
          </div>
          {kz.w6_stabilitaet != null && (
            <div className="kennzahl">
              <b>{String((kz.w6_stabilitaet as Record<string, number>).erhalten)}</b>
              <span>Zuweisungen erhalten ({String((kz.w6_stabilitaet as Record<string, number>).neu)} neu)</span>
            </div>
          )}
        </div>
      </div>

      <div className="zeile">
        <div className="karte" style={{ flex: 3, minWidth: 640 }}>
          <div className="zeile" style={{ alignItems: "center", marginBottom: "0.5rem" }}>
            <div>
              {(["Fr", "Sa"] as const).map((t) => (
                <button
                  key={t}
                  className={`klein ${tag === t ? "" : "sekundaer"}`}
                  style={{ marginRight: 4 }}
                  onClick={() => setTag(t)}
                >
                  {t === "Fr" ? "Freitag" : "Samstag"}
                </button>
              ))}
            </div>
            <div>
              {(
                [
                  ["raeume", "Räume"],
                  ["bewerbende", "Bewerbende"],
                  ["pruefende", "Prüfende"],
                ] as const
              ).map(([wert, label]) => (
                <button
                  key={wert}
                  className={`klein ${sicht === wert ? "" : "sekundaer"}`}
                  style={{ marginRight: 4 }}
                  onClick={() => setSicht(wert)}
                >
                  Sicht: {label}
                </button>
              ))}
            </div>
            <span className="hinweis">Klick auf einen Block öffnet die Umbuchung.</span>
          </div>
          <Planungsraster
            plan={plan}
            tag={tag}
            sicht={sicht}
            markiert={markiert}
            onAuswahl={setAuswahl}
          />
        </div>

        <div className="karte" style={{ flex: 1, minWidth: 320 }}>
          <h3 style={{ marginTop: 0 }}>Konflikte</h3>
          <Konfliktliste konflikte={plan.konflikte} onSpringen={springen} />
        </div>
      </div>

      {auswahl && (
        <UmbuchungsDialog
          jahrgangId={jahrgangId}
          zuweisung={auswahl}
          plan={plan}
          pruefende={pruefende}
          onSchliessen={() => setAuswahl(null)}
          onUebernommen={async () => {
            setAuswahl(null);
            setMarkiert(new Set());
            await laden();
          }}
        />
      )}
    </>
  );
}
