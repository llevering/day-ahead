import sys
from pathlib import Path

sys.path.append("../../")
from dao.prog.config.loader import ConfigurationLoader
from dao.prog.config.models.dashboard import DashboardConfig

app_datapath = "app/static/data/"
try:
    _loader = ConfigurationLoader(Path(app_datapath + "options.json"))
    _config = _loader.load_and_validate()
    port = _config.dashboard.port
except Exception:
    port = DashboardConfig().port
workers = 2
bind = f"0.0.0.0:{port}"
forwarded_allow_ips = "*"
secure_scheme_headers = {"X-Forwarded-Proto": "https"}
# Tasks started via /api/run/<task> run inside the request; an optimisation with
# an EV to plan can take several minutes and the worker (and the task) would be
# killed when the request exceeds this timeout.
timeout = 600
