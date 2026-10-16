"""
show_graph.py

Mostra il tasso di occupazione (dal db SQLite creato da Istat.export_db (istat.py)) nel tempo,
con una linea di colore diverso per ogni fascia d'età.

Uso:
  python show_graph.py [--db employment.sqlite] [--area IT] [--sex 9]
                       [--freq Q] [--edu 99] [--citizenship TOTAL]
                       [--save grafico.png]

  --area  codice REF_AREA (IT, ITC, ITD, ITE, ITFG, ITCD)
  --sex   1 = maschi, 2 = femmine, 9 = totale
  --freq  Q = trimestrale, A = annuale
  --edu   codice EDU_LEV_HIGHEST: 99 = totale, 7 = diploma, 11 = laurea e
          post-laurea, 13 = nessun titolo/licenza elementare e media
  --citizenship  TOTAL, ITL (italiano-a) o FRG (straniero-a); con valori
          diversi da TOTAL le fasce d'età disponibili sono poche
  --save  salva su file invece di aprire la finestra
"""

import argparse
import re
import sqlite3
from datetime import date

import matplotlib.pyplot as plt


def period_to_date(period):
    """'2004' -> 2004-01-01, '2004-Q3' -> 2004-07-01."""
    m = re.fullmatch(r"(\d{4})(?:-Q([1-4]))?", period)
    year, quarter = int(m.group(1)), int(m.group(2) or 1)
    return date(year, 3 * (quarter - 1) + 1, 1)


def age_sort_key(code):
    """Ordina 'Y15-24', 'Y15-64', ... per età iniziale e poi finale."""
    a, b = re.fullmatch(r"Y(\d+)-(\d+)", code).groups()
    return int(a), int(b)


def describe(db, edu, citizenship):
    """Suffisso del titolo del grafico con titolo di studio e cittadinanza."""
    con = sqlite3.connect(db)
    parts = []
    for codelist, code, total in (
        ("CL_TITOLO_STUDIO", edu, "99"),
        ("CL_CITTADINANZA", citizenship, "TOTAL"),
    ):
        if code != total:
            row = con.execute(
                "SELECT name_it FROM code WHERE codelist_id = ? AND code = ?",
                (codelist, code),
            ).fetchone()
            parts.append(row[0] if row else code)
    con.close()
    return "".join(f", {p}" for p in parts)


def load(db, area, sex, freq, edu="99", citizenship="TOTAL"):
    """Restituisce {(codice_età, etichetta): ([date], [valori])}."""
    con = sqlite3.connect(db)
    rows = con.execute(
        """
        SELECT AGE, AGE_it, TIME_PERIOD, value
        FROM observation_label
        WHERE REF_AREA = ? AND SEX = ? AND FREQ = ?
          AND EDU_LEV_HIGHEST = ? AND CITIZENSHIP = ? AND value IS NOT NULL
        ORDER BY TIME_PERIOD
        """,
        (area, sex, freq, edu, citizenship),
    ).fetchall()
    meta = con.execute(
        """
        SELECT
          (SELECT name_it FROM code WHERE codelist_id = 'CL_ITTER107' AND code = ?),
          (SELECT name_it FROM code WHERE codelist_id = 'CL_SEXISTAT1' AND code = ?)
        """,
        (area, sex),
    ).fetchone()
    con.close()

    series = {}
    for age, label, period, value in rows:
        xs, ys = series.setdefault((age, label), ([], []))
        xs.append(period_to_date(period))
        ys.append(value)
    return series, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="employment.sqlite")
    ap.add_argument("--area", default="IT")
    ap.add_argument("--sex", default="9", choices=["1", "2", "9"])
    ap.add_argument("--freq", default="Q", choices=["Q", "A"])
    ap.add_argument("--edu", default="99")
    ap.add_argument("--citizenship", default="TOTAL")
    ap.add_argument("--save")
    args = ap.parse_args()

    series, (area_name, sex_name) = load(
        args.db, args.area, args.sex, args.freq, args.edu, args.citizenship
    )
    if not series:
        raise SystemExit("Nessun dato per i filtri richiesti.")

    ages = sorted(series, key=lambda k: age_sort_key(k[0]))
    # colormap con 20 colori distinti, abbastanza per le 16 fasce d'età
    cmap = plt.get_cmap("tab20")

    fig, ax = plt.subplots(figsize=(12, 6.5))
    for i, key in enumerate(ages):
        xs, ys = series[key]
        ax.plot(xs, ys, color=cmap(i), linewidth=1.6, label=key[1])

    ax.set_xlabel("Tempo")
    ax.set_ylabel("Tasso di occupazione (%)")
    extra = describe(args.db, args.edu, args.citizenship)
    ax.set_title(
        f"Tasso di occupazione per fascia d'età - {area_name}, {sex_name}{extra}"
    )
    ax.grid(True, alpha=0.3)
    ax.legend(title="Fascia d'età", loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.tight_layout()

    if args.save:
        fig.savefig(args.save, dpi=150)
        print(f"Salvato in {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
