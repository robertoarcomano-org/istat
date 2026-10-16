"""
show_graph_3d_surface.py

Superficie 3D del tasso di occupazione (dal db SQLite creato da Istat.export_db (istat.py)):
  x = tempo, y = area geografica, z = tasso di occupazione (anche colore).
Per una fascia d'età scelta.

Nella finestra il modello si ruota a mano trascinando col mouse (tasto sinistro);
con il tasto destro trascinato si fa zoom.

Per default usa le quattro ripartizioni, da Nord a Sud (Nord-ovest, Nord-est,
Centro, Mezzogiorno), che sono adiacenti e non sovrapposte: una superficie
tra "Italia" e "Nord" (che ne è una parte) non avrebbe senso. Con --all-areas
si aggiungono anche Italia e Nord.

Uso:
  python show_graph_3d_surface.py [--db employment.sqlite] [--age Y15-64]
                                  [--sex 9] [--freq Q] [--edu 99]
                                  [--citizenship TOTAL] [--all-areas]
                                  [--smooth 8] [--save grafico.png]
"""

import argparse

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import PchipInterpolator

from show_graph import describe, period_to_date
from show_graph_3d import load

REGIONS = ["ITC", "ITD", "ITE", "ITFG"]
ALL_AREAS = ["IT", "ITCD"] + REGIONS


def make_parser(description=None):
    ap = argparse.ArgumentParser(description=description or __doc__.split("\n\n")[0])
    ap.add_argument("--db", default="employment.sqlite")
    ap.add_argument("--age", default="Y15-64")
    ap.add_argument("--sex", default="9", choices=["1", "2", "9"])
    ap.add_argument("--freq", default="Q", choices=["Q", "A"])
    ap.add_argument("--edu", default="99", help="vedi show_graph_3d.py")
    ap.add_argument("--citizenship", default="TOTAL")
    ap.add_argument("--all-areas", action="store_true")
    ap.add_argument(
        "--smooth", type=int, default=1, metavar="N",
        help="interpola la superficie con N punti in più per ogni intervallo "
             "(1 = nessuna interpolazione; 6-10 per una superficie morbida)",
    )
    ap.add_argument("--save")
    return ap


def build_data(args):
    """Legge il db e restituisce la griglia: (x, Z, nomi_aree, titolo).

    x sono le date come numeri matplotlib; Z ha una riga per area e una
    colonna per periodo. Con --smooth la griglia viene interpolata.
    """
    wanted = ALL_AREAS if args.all_areas else REGIONS
    series, age_name, sex_name = load(
        args.db, args.age, args.sex, args.freq, args.edu, args.citizenship, wanted
    )
    areas = [a for a in wanted if a in series]
    if not areas:
        raise SystemExit("Nessun dato per i filtri richiesti.")

    # una superficie richiede una griglia completa: tengo solo i periodi
    # presenti in tutte le aree
    by_area = {a: dict(zip(series[a][1], series[a][2])) for a in areas}
    dates = sorted(set.intersection(*(set(d) for d in by_area.values())))
    dropped = len(set.union(*(set(d) for d in by_area.values()))) - len(dates)
    if dropped:
        print(f"Scartati {dropped} periodi non presenti in tutte le aree")

    x = mdates.date2num(dates)
    Z = np.array([[by_area[a][d] for d in dates] for a in areas])
    names = [series[a][0] for a in areas]
    extra = describe(args.db, args.edu, args.citizenship)
    title = f"Tasso di occupazione per area - {age_name}, {sex_name}{extra}"
    return x, Z, names, title


def smooth_grid(x, Z, factor):
    """Interpola la griglia, `factor` volte più fitta, con spline PCHIP.

    Restituisce (x, y, Z) con y in coordinate d'indice delle aree (0, 1, ...).
    PCHIP passa per tutti i punti reali e non supera mai i valori vicini
    (una spline cubica con sole quattro aree creerebbe colline fittizie tra
    un'area e l'altra). I punti in più sono interpolazione, non dati.
    """
    y = np.arange(Z.shape[0])
    if factor <= 1:
        return x, y, Z
    xs = np.linspace(x[0], x[-1], (len(x) - 1) * factor + 1)
    ys = np.linspace(y[0], y[-1], (len(y) - 1) * factor + 1)
    Zt = PchipInterpolator(x, Z, axis=1)(xs)  # lungo il tempo
    return xs, ys, PchipInterpolator(y, Zt, axis=0)(ys)  # tra le aree


def build_figure(args):
    """Crea la figura con la superficie. Restituisce (fig, ax)."""
    x, Z, names, title = build_data(args)
    xs, ys, Zs = smooth_grid(x, Z, args.smooth)
    X, Y = np.meshgrid(xs, ys)

    fig = plt.figure(figsize=(12, 7))
    ax = fig.add_subplot(projection="3d")
    surf = ax.plot_surface(
        X, Y, Zs, cmap="viridis", antialiased=True,
        # le linee bianche della griglia servono solo sui dati originali
        **({"edgecolor": "white", "linewidth": 0.2} if args.smooth <= 1
           else {"linewidth": 0, "rstride": 1, "cstride": 1}),
    )
    fig.colorbar(surf, ax=ax, shrink=0.6, pad=0.1, label="Tasso di occupazione (%)")

    ax.xaxis.set_major_locator(mdates.YearLocator(4))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("Tempo")
    ax.set_ylabel("Area")
    ax.set_zlabel("Tasso di occupazione (%)")
    ax.set_title(title)
    fig.tight_layout()
    return fig, ax


def main():
    args = make_parser().parse_args()
    fig, _ = build_figure(args)

    if args.save:
        fig.savefig(args.save, dpi=150)
        print(f"Salvato in {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
