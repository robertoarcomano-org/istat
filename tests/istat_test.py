import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from istat import Istat


def test_prints_ok(capsys):
    _ = Istat()
    captured = capsys.readouterr()
    assert captured.out == "Downloading data from Istat...\nData downloaded.\n"
    assert captured.err == ""
