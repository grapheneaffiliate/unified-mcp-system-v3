import importlib, json
from typing import Any

def load_and_register_from_file(registry: Any, path: str):
    # supports YAML or JSON
    try:
        if path.endswith((".yml", ".yaml")):
            import yaml  # type: ignore
            with open(path, "r") as f:
                conf = yaml.safe_load(f)
        else:
            with open(path, "r") as f:
                conf = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed reading tools config {path}: {e}")

    mods = conf.get("modules", [])
    if not isinstance(mods, list):
        raise RuntimeError("Invalid tools config: modules[] expected")

    for mod in mods:
        if not mod.get("enabled", True):
            continue
        strict = bool(mod.get("strict", True))
        module_name = mod["module"]
        reg_fn = mod.get("register", "register_toolset")
        try:
            m = importlib.import_module(module_name)
            getattr(m, reg_fn)(registry)
        except Exception as e:
            if strict:
                raise RuntimeError(f"Failed registering {module_name}.{reg_fn}: {e}")
            print(f"[registry_loader] WARN: Skipping {module_name}.{reg_fn} due to error: {e}")
