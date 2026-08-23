"""
read_unemployment.py

Legge i file SDMX-ML (struttura + dati) della disoccupazione ISTAT
e produce un dataframe con: sesso (in italiano), fascia d'età,
periodo di riferimento e valore.
"""

import sdmx
import pandas as pd


def get_label_it(code) -> str:
    """Estrae l'etichetta italiana di un Code SDMX, con fallback."""
    name = code.name
    # A seconda della versione di sdmx1, InternationalString espone
    # .localizations (dict) oppure .localized_default(lang)
    if hasattr(name, "localizations"):
        return name.localizations.get("it") or str(name)
    try:
        return name.localized_default("it")
    except Exception:
        return str(name)


def main():
    structure_path = "structure.xml"
    data_path = "data.xml"

    sm = sdmx.read_sdmx(structure_path)
    dsd = sm.structure[0]

    msg = sdmx.read_sdmx(data_path, dsd=dsd)
    df = sdmx.to_pandas(msg).reset_index()

    # Trova il nome esatto della codelist del sesso associata alla DSD
    sex_codelist_id = None
    for dim in dsd.dimensions:
        if dim.id == "SEX":
            enumerated = getattr(dim.local_representation, "enumerated", None)
            if enumerated is not None:
                sex_codelist_id = enumerated.id
            break

    if sex_codelist_id is None:
        raise RuntimeError(
            "Non trovo la codelist per la dimensione SEX. "
            f"Codelist disponibili: {list(sm.codelist.keys())}"
        )

    cl_sex = sm.codelist[sex_codelist_id]
    mappa_sesso = {c.id: get_label_it(c) for c in cl_sex}

    df["SEX"] = df["SEX"].map(mappa_sesso).fillna(df["SEX"])

    risultato = df[["SEX", "AGE", "TIME_PERIOD", "value"]].rename(
        columns={
            "SEX": "sesso",
            "AGE": "eta",
            "TIME_PERIOD": "periodo",
            "value": "valore",
        }
    )

    return risultato


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    df_finale = main()
    # print(df_finale.head(20))
    print(df_finale)

    # opzionale: salva su disco
    df_finale.to_csv("disoccupazione.csv", index=False)