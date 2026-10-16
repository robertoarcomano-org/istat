"""
show_graph_3d.py

Grafico 3D del tasso di occupazione (dal db SQLite creato da Istat.export_db (istat.py)):
  x = tempo, y = area geografica, z = tasso di occupazione.
Una linea di colore diverso per ogni area, per una fascia d'età scelta.

Uso:
  python show_graph_3d.py [--db employment.sqlite] [--age Y15-64] [--sex 9]
                          [--freq Q] [--edu 99] [--citizenship TOTAL]
                          [--areas IT,ITC,...] [--save grafico.png]

  --age   codice AGE (es. Y15-24, Y15-64, Y25-34, ...)
  --sex   1 = maschi, 2 = femmine, 9 = totale
  --freq  Q = trimestrale, A = annuale
  --edu   codice EDU_LEV_HIGHEST (99 = totale, 7 = diploma, 11 = laurea e
          post-laurea, 13 = nessun titolo/licenza elementare e media)
  --citizenship  TOTAL, ITL (italiano-a) o FRG (straniero-a)
  --areas codici REF_AREA separati da virgola (default: Italia, Nord e le
          quattro ripartizioni; nel db ci sono anche regioni e province)
  --save  salva su file invece di aprire la finestra
"""

import argparse
import sqlite3

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from show_graph import describe, period_to_date

# Ordine di visualizzazione: Italia, Nord (= Nord-ovest + Nord-est), poi le ripartizioni
AREA_ORDER = ["IT", "ITCD", "ITC", "ITD", "ITE", "ITFG"]


def load(db, age, sex, freq, edu="99", citizenship="TOTAL", areas=None):
    """Restituisce ({area: (etichetta, [date], [valori])}, etichetta_età, etichetta_sesso)."""
    areas = list(areas or AREA_ORDER)
    con = sqlite3.connect(db)
    rows = con.execute(
        f"""
        SELECT REF_AREA, REF_AREA_it, TIME_PERIOD, value
        FROM observation_label
        WHERE AGE = ? AND SEX = ? AND FREQ = ?
          AND EDU_LEV_HIGHEST = ? AND CITIZENSHIP = ? AND value IS NOT NULL
          AND REF_AREA IN ({", ".join("?" * len(areas))})
        ORDER BY TIME_PERIOD
        """,
        (age, sex, freq, edu, citizenship, *areas),
    ).fetchall()
    meta = con.execute(
        """
        SELECT
          (SELECT name_it FROM code WHERE codelist_id = 'CL_ETA1' AND code = ?),
          (SELECT name_it FROM code WHERE codelist_id = 'CL_SEXISTAT1' AND code = ?)
        """,
        (age, sex),
    ).fetchone()
    con.close()

    series = {}
    for area, label, period, value in rows:
        _, xs, ys = series.setdefault(area, (label, [], []))
        xs.append(period_to_date(period))
        ys.append(value)
    return series, *meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="employment.sqlite")
    ap.add_argument("--age", default="Y15-64")
    ap.add_argument("--sex", default="9", choices=["1", "2", "9"])
    ap.add_argument("--freq", default="Q", choices=["Q", "A"])
    ap.add_argument("--edu", default="99")
    ap.add_argument("--citizenship", default="TOTAL")
    ap.add_argument("--areas", type=lambda v: v.split(","))
    ap.add_argument("--save")
    args = ap.parse_args()

    series, age_name, sex_name = load(
        args.db, args.age, args.sex, args.freq, args.edu, args.citizenship, args.areas
    )
    if not series:
        raise SystemExit("Nessun dato per i filtri richiesti.")

    areas = [a for a in AREA_ORDER if a in series] + sorted(set(series) - set(AREA_ORDER))
    cmap = plt.get_cmap("tab10")

    fig = plt.figure(figsize=(12, 7))
    ax = fig.add_subplot(projection="3d")
    for i, area in enumerate(areas):
        label, xs, ys = series[area]
        ax.plot(
            mdates.date2num(xs), [i] * len(xs), ys,
            color=cmap(i), linewidth=1.8, label=label,
        )

    ax.xaxis.set_major_locator(mdates.YearLocator(4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_yticks(range(len(areas)))
    ax.set_yticklabels([series[a][0] for a in areas], fontsize=8)
    ax.set_xlabel("Tempo")
    ax.set_ylabel("Area")
    ax.set_zlabel("Tasso di occupazione (%)")
    extra = describe(args.db, args.edu, args.citizenship)
    ax.set_title(f"Tasso di occupazione per area - {age_name}, {sex_name}{extra}")
    ax.legend(title="Area", loc="center left", bbox_to_anchor=(1.05, 0.5))
    fig.tight_layout()

    if args.save:
        fig.savefig(args.save, dpi=150)
        print(f"Salvato in {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
