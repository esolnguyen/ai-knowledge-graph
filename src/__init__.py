"""aikgraph - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `aikgraph install` works before heavy deps are in place.
    _map = {
        "extract": ("aikgraph.extraction.extract", "extract"),
        "collect_files": ("aikgraph.extraction.extract", "collect_files"),
        "build_from_json": ("aikgraph.core.build", "build_from_json"),
        "cluster": ("aikgraph.core.cluster", "cluster"),
        "score_all": ("aikgraph.core.cluster", "score_all"),
        "cohesion_score": ("aikgraph.core.cluster", "cohesion_score"),
        "god_nodes": ("aikgraph.core.analyze", "god_nodes"),
        "surprising_connections": ("aikgraph.core.analyze", "surprising_connections"),
        "suggest_questions": ("aikgraph.core.analyze", "suggest_questions"),
        "generate": ("aikgraph.output.report", "generate"),
        "to_json": ("aikgraph.output.json_export", "to_json"),
        "to_html": ("aikgraph.output.html", "to_html"),
        "to_svg": ("aikgraph.output.svg", "to_svg"),
        "to_canvas": ("aikgraph.output.obsidian", "to_canvas"),
        "to_wiki": ("aikgraph.output.wiki", "to_wiki"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'aikgraph' has no attribute {name!r}")
