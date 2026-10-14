import os

import requests


class Istat:
    data = {
        "employment": {
            "structure": "https://esploradati.istat.it/SDMXWS/rest/dataflow/IT1/150_915_DF_DCCV_TAXOCCU1_1/1.0/?detail=Full&references=Descendants",
            "data": "https://esploradati.istat.it/SDMXWS/rest/data/IT1,150_915_DF_DCCV_TAXOCCU1_1,1.0/all/ALL/?detail=full&startPeriod=2024-04-01&endPeriod=2026-06-30&dimensionAtObservation=TIME_PERIOD",
        }
    }
    
    @staticmethod
    def save_url(url, filename):
        if os.path.exists(filename):
            return
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(filename, "wb") as f:
            f.write(response.content)

    def get_data(self):
        for datatype, urls in self.data.items():
            for kind, url in urls.items():
                self.save_url(url, f"{datatype}_{kind}.xml")

    def __init__(self):
        print("Downloading data from Istat...")
        self.get_data()
        print("Data downloaded.")


