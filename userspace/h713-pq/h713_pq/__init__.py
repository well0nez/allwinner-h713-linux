"""h713-pq -- read the stock PQ data of the HY310 and convert it into kernel interfaces.

Three modules, strictly separated:
    sources  -- reads (SQLite, INI, XML), computes nothing
    model    -- computes (chain input x picture mode -> target values), reads nothing
    output   -- prints and writes files, computes nothing
"""

__version__ = "0.1"
