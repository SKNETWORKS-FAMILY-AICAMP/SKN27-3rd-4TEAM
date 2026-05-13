from common.graphs.diagnosis_graph import build_diagnosis_graph, run_diagnosis
from common.graphs.legal_consultation_graph import build_legal_consultation_graph, run_legal_consultation
from common.graphs.defense_simulation_graph import build_defense_simulation_graph, run_defense_simulation
from common.graphs.supervisor_graph import build_supervisor_graph, run_supervisor

__all__ = [
    "build_diagnosis_graph", "run_diagnosis",
    "build_legal_consultation_graph", "run_legal_consultation",
    "build_defense_simulation_graph", "run_defense_simulation",
    "build_supervisor_graph", "run_supervisor",
]
