import json
import os
import sqlite3
import sys
from xml.etree import ElementTree as ET

import requests

BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"

NS_STR = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}"
NS_COM = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common}"
NS_GEN = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

BATCH = 5000

# Dataflow del tasso di occupazione (famiglia 150_915_DF_DCCV_TAXOCCU1_*).
# Hanno tutti le stesse dimensioni, ma contengono combinazioni diverse di
# titolo di studio, cittadinanza, età e territorio.
EMPLOYMENT_DATAFLOWS = {
    "1": "Classe di età",
    "2": "Titolo di studio, età",
    "3": "Titolo di studio, cittadinanza, età",
    "4": "Dati regionali",
    "5": "Dati provinciali",
    "6": "Dal I 2004 - età",
    # "YOUTH_1" (Giovani - dati annuali e trimestrali): il server di ISTAT va
    # sempre in timeout sui dati, quindi è escluso
}


def employment_urls(suffix):
    flow = f"150_915_DF_DCCV_TAXOCCU1_{suffix}"
    return {
        "structure": f"{BASE_URL}/dataflow/IT1/{flow}/1.0/?detail=Full&references=Descendants",
        "data": f"{BASE_URL}/data/IT1,{flow},1.0/all/ALL/?detail=full&dimensionAtObservation=AllDimensions",
    }


class Istat:
    """Scarica i dati ISTAT (SDMX-ML) e li esporta in un database SQLite.

    I file scaricati si chiamano employment_<suffix>_structure.xml e
    employment_<suffix>_data.xml. Con export_db() i dati di tutti i dataflow
    finiscono in un unico db.

    I dataflow hanno le stesse dimensioni e si sovrappongono in parte: ogni
    combinazione di dimensioni compare una sola volta in observation, con
    l'indicazione del primo dataflow che la contiene. Se lo stesso punto
    compare in più dataflow con valori diversi, export_db lo segnala.

    Tabelle:
      dataflow(id, name_it)
      codelist(id, name_it, name_en)
      code(codelist_id, code, name_it, name_en, parent)
      dimension(id, position, codelist_id)   -- codelist_id NULL per TIME_PERIOD
      observation(id, dataflow, <una colonna per dimensione>, value, attributes)

    Vista:
      observation_label  -- observation con una colonna <DIM>_it per ogni
                            dimensione dotata di codelist (etichetta italiana)

    Da riga di comando:  python istat.py [db.sqlite]
    """

    # nome -> {"structure": url, "data": url}
    data = {
        f"employment_{suffix}": employment_urls(suffix)
        for suffix in EMPLOYMENT_DATAFLOWS
    }

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    @staticmethod
    def save_url(url, filename):
        if os.path.exists(filename):
            return
        response = requests.get(url, timeout=(10, 200))
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)

    def get_data(self):
        for datatype, urls in self.data.items():
            for kind, url in urls.items():
                try:
                    self.save_url(url, f"{datatype}_{kind}.xml")
                except requests.RequestException as e:
                    # es. il dataflow YOUTH_1 va sempre in timeout lato server
                    print(f"Skipped {datatype} {kind}: {e}", file=sys.stderr)

    def __init__(self):
        print("Downloading data from Istat...")
        self.get_data()
        print("Data downloaded.")

    # ------------------------------------------------------------------
    # Lettura dei file SDMX-ML
    # ------------------------------------------------------------------

    @staticmethod
    def _names(elem):
        """Restituisce {lingua: testo} dei figli common:Name di un elemento."""
        return {n.get(XML_LANG): (n.text or "") for n in elem.findall(NS_COM + "Name")}

    @classmethod
    def _load_structure(cls, path):
        """Restituisce (codelists, dimensions).

        codelists:  {id: (names, [(code, names, parent), ...])}
        dimensions: [(id, position, codelist_id | None)] ordinate per posizione
        """
        codelists = {}
        dimensions = []
        for _, e in ET.iterparse(path):
            if e.tag == NS_STR + "Codelist":
                codes = []
                for c in e.findall(NS_STR + "Code"):
                    parent = c.find(f"{NS_STR}Parent/Ref")
                    codes.append(
                        (c.get("id"), cls._names(c),
                         parent.get("id") if parent is not None else None)
                    )
                codelists[e.get("id")] = (cls._names(e), codes)
                e.clear()
            elif e.tag == NS_STR + "DimensionList":
                for d in e:
                    if d.tag == NS_STR + "TimeDimension":
                        dimensions.append((d.get("id"), int(d.get("position")), None))
                    elif d.tag == NS_STR + "Dimension":
                        ref = d.find(f"{NS_STR}LocalRepresentation/{NS_STR}Enumeration/Ref")
                        dimensions.append(
                            (d.get("id"), int(d.get("position")),
                             ref.get("id") if ref is not None else None)
                        )
        dimensions.sort(key=lambda d: d[1])
        return codelists, dimensions

    @staticmethod
    def _iter_observations(path):
        """Genera (dims: dict, value: str | None, attributes: dict) per ogni Obs."""
        for _, e in ET.iterparse(path):
            if e.tag != NS_GEN + "Obs":
                continue
            dims = {v.get("id"): v.get("value") for v in e.find(NS_GEN + "ObsKey")}
            ov = e.find(NS_GEN + "ObsValue")
            value = ov.get("value") if ov is not None else None
            attrs = e.find(NS_GEN + "Attributes")
            attributes = {v.get("id"): v.get("value") for v in attrs} if attrs is not None else {}
            yield dims, value, attributes
            e.clear()

    # ------------------------------------------------------------------
    # Scrittura su SQLite
    # ------------------------------------------------------------------

    @staticmethod
    def _create_schema(con, dim_ids):
        cols = ",\n    ".join(f'"{d}" TEXT NOT NULL' for d in dim_ids)
        con.executescript(
            f"""
            DROP VIEW  IF EXISTS observation_label;
            DROP TABLE IF EXISTS observation;
            DROP TABLE IF EXISTS dataflow;
            DROP TABLE IF EXISTS dimension;
            DROP TABLE IF EXISTS code;
            DROP TABLE IF EXISTS codelist;

            CREATE TABLE dataflow (
                id      TEXT PRIMARY KEY,
                name_it TEXT
            );
            CREATE TABLE codelist (
                id      TEXT PRIMARY KEY,
                name_it TEXT,
                name_en TEXT
            );
            CREATE TABLE code (
                codelist_id TEXT NOT NULL REFERENCES codelist(id),
                code        TEXT NOT NULL,
                name_it     TEXT,
                name_en     TEXT,
                parent      TEXT,
                PRIMARY KEY (codelist_id, code)
            );
            CREATE TABLE dimension (
                id          TEXT PRIMARY KEY,
                position    INTEGER NOT NULL,
                codelist_id TEXT REFERENCES codelist(id)
            );
            CREATE TABLE observation (
                id INTEGER PRIMARY KEY,
                dataflow TEXT NOT NULL REFERENCES dataflow(id),
                {cols},
                value      REAL,
                attributes TEXT,
                UNIQUE ({", ".join(f'"{d}"' for d in dim_ids)})
            );
            """
        )

    @staticmethod
    def _create_view(con, dimensions):
        selects, joins = ["o.*"], []
        for dim_id, _, cl in dimensions:
            if cl is None:
                continue
            a = f"c_{dim_id}"
            selects.append(f'{a}.name_it AS "{dim_id}_it"')
            joins.append(
                f"LEFT JOIN code {a} ON {a}.codelist_id = '{cl}' AND {a}.code = o.\"{dim_id}\""
            )
        con.execute(
            f"CREATE VIEW observation_label AS SELECT {', '.join(selects)} "
            f"FROM observation o {' '.join(joins)}"
        )

    @classmethod
    def _load_flow(cls, con, flow_id, data_path, dim_ids):
        """Carica le osservazioni di un dataflow, saltando quelle già presenti.

        Restituisce (inserite, già presenti, già presenti con valore diverso).
        """
        dim_cols = ", ".join(f'"{d}"' for d in dim_ids)
        con.execute(f"CREATE TEMP TABLE staging ({dim_cols}, value REAL, attributes TEXT)")
        sql = f"INSERT INTO staging VALUES ({', '.join('?' * (len(dim_ids) + 2))})"
        batch, total = [], 0
        for dims, value, attributes in cls._iter_observations(data_path):
            batch.append(
                [dims[d] for d in dim_ids]
                + [float(value) if value not in (None, "") else None,
                   json.dumps(attributes) if attributes else None]
            )
            if len(batch) >= BATCH:
                con.executemany(sql, batch)
                total += len(batch)
                batch.clear()
        con.executemany(sql, batch)
        total += len(batch)

        same = " AND ".join(f'o."{d}" = s."{d}"' for d in dim_ids)
        # conflitti: stesso punto già inserito da un altro dataflow, valore diverso
        conflicts = con.execute(
            f"SELECT COUNT(*) FROM staging s JOIN observation o ON {same} "
            f"WHERE o.dataflow <> ? AND o.value IS NOT s.value",
            (flow_id,),
        ).fetchone()[0]
        cur = con.execute(
            f"INSERT OR IGNORE INTO observation (dataflow, {dim_cols}, value, attributes) "
            f"SELECT ?, {dim_cols}, value, attributes FROM staging",
            (flow_id,),
        )
        inserted = cur.rowcount
        con.execute("DROP TABLE staging")
        return inserted, total - inserted, conflicts

    def export_db(self, db_path="employment.sqlite"):
        """Salva struttura e dati di tutti i dataflow scaricati in un db SQLite.

        Il db viene ricreato da zero a ogni chiamata. I dataflow i cui file
        non sono stati scaricati vengono saltati.
        """
        flows = []
        for suffix, name in EMPLOYMENT_DATAFLOWS.items():
            structure_path = f"employment_{suffix}_structure.xml"
            data_path = f"employment_{suffix}_data.xml"
            if not (os.path.exists(structure_path) and os.path.exists(data_path)):
                print(f"Dataflow {suffix}: file mancanti, saltato")
                continue
            flows.append((suffix, name, structure_path, data_path))
        if not flows:
            raise FileNotFoundError("Nessun file scaricato: impossibile creare il db")

        con = sqlite3.connect(db_path)
        try:
            dimensions = None
            with con:
                for suffix, name, structure_path, data_path in flows:
                    codelists, dims = self._load_structure(structure_path)
                    if dimensions is None:
                        dimensions = dims
                        dim_ids = [d[0] for d in dimensions]
                        self._create_schema(con, dim_ids)
                        con.executemany("INSERT INTO dimension VALUES (?, ?, ?)", dimensions)
                    elif dims != dimensions:
                        raise ValueError(f"Dataflow {suffix}: dimensioni diverse dagli altri")

                    con.execute("INSERT INTO dataflow VALUES (?, ?)", (suffix, name))
                    con.executemany(
                        "INSERT OR REPLACE INTO codelist VALUES (?, ?, ?)",
                        [(cid, n.get("it"), n.get("en")) for cid, (n, _) in codelists.items()],
                    )
                    con.executemany(
                        "INSERT OR REPLACE INTO code VALUES (?, ?, ?, ?, ?)",
                        [
                            (cid, code, n.get("it"), n.get("en"), parent)
                            for cid, (_, codes) in codelists.items()
                            for code, n, parent in codes
                        ],
                    )

                    inserted, dup, conflicts = self._load_flow(con, suffix, data_path, dim_ids)
                    print(
                        f"Dataflow {suffix:8} {name}: {inserted} nuove osservazioni, "
                        f"{dup} già presenti"
                        + (f", {conflicts} CON VALORE DIVERSO" if conflicts else "")
                    )

                self._create_view(con, dimensions)

            total = con.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
            n_codes = con.execute("SELECT COUNT(*) FROM code").fetchone()[0]
            print(f"{db_path}: {len(flows)} dataflow, {n_codes} codici, {total} osservazioni")
        finally:
            con.close()


if __name__ == "__main__":
    Istat().export_db(sys.argv[1] if len(sys.argv) > 1 else "employment.sqlite")
