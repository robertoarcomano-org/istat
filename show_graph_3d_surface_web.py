"""
show_graph_3d_surface_web.py

Come show_graph_3d_surface.py, ma produce una pagina web (HTML con Plotly)
che si apre nel browser: il modello si ruota trascinando col mouse, si fa
zoom con la rotella e passando sopra la superficie si leggono area, periodo
e valore.

Uso:
  python show_graph_3d_surface_web.py [opzioni di show_graph_3d_surface.py]
                                      [--out superficie.html] [--no-open]

L'HTML è autonomo (include Plotly): si può aprire o condividere senza server
e senza connessione.
"""

import webbrowser
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import plotly.graph_objects as go

from show_graph_3d_surface import build_data, make_parser, smooth_grid


def main():
    ap = make_parser(__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="superficie.html")
    ap.add_argument("--no-open", action="store_true", help="non aprire il browser")
    ap.set_defaults(smooth=8)  # sul web l'interpolazione è attiva di default
    args = ap.parse_args()

    x, Z, names, title = build_data(args)
    xs, ys, Zs = smooth_grid(x, Z, args.smooth)
    dates = [d.strftime("%Y-%m-%d") for d in mdates.num2date(xs)]

    # nel tooltip mostro il nome dell'area più vicina (la y è continua)
    area_at = np.array(names)[np.clip(np.rint(ys).astype(int), 0, len(names) - 1)]
    area_grid = np.repeat(area_at[:, None], len(xs), axis=1)

    fig = go.Figure(
        go.Surface(
            x=dates, y=ys, z=Zs, customdata=area_grid,
            colorscale="Viridis",
            colorbar=dict(title="Tasso di<br>occupazione (%)"),
            hovertemplate="%{customdata}<br>%{x|%Y-%m}<br>%{z:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis_title="Tempo",
            yaxis=dict(
                title="Area",
                tickmode="array",
                tickvals=list(range(len(names))),
                ticktext=names,
            ),
            zaxis_title="Tasso di occupazione (%)",
            camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
        ),
        margin=dict(l=0, r=0, t=50, b=0),
    )

    out = Path(args.out)
    fig.write_html(out, include_plotlyjs=True)
    print(f"Salvato in {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
