import json
from collections.abc import Iterable, Mapping


class LocalsManager:

    def __init__(self):
        self.ignored_vars = None
        self.local_variables = {}

    def update_locals(self, frame, ignored_vars=None):
        self.ignored_vars = ignored_vars
        self.local_variables = self._filter_frame_locals(frame)

    def _filter_frame_locals(self, frame):

        def to_safe(value):
            try:
                json.dumps(value)
                return value
            except (TypeError, OverflowError):
                return {"__type__": type(value).__name__, "__repr__": repr(value)}

        def sanitize(obj):
            if isinstance(obj, Mapping):
                return {k: sanitize(v) for k, v in obj.items()}

            if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
                return [sanitize(v) for v in obj]

            return to_safe(obj)

        if self.ignored_vars == None:
            self.ignored_vars = {}

        local_vars = {k: v for k, v in frame.f_locals.items() if k not in self.ignored_vars}

        return sanitize(local_vars)

    def format_frame_vars(self, frame_vars: dict, max_collection_len=30, max_str_len=150, max_depth=10) -> list:
        def _inspect(name, val, depth):
            var_type = type(val).__name__
            var_info = {
                "name": str(name),
                "type": var_type,
                "has_children": False,
                "children": []
            }

            if depth > max_depth:
                var_info["value"] = "<Max Depth Reached>"
                return var_info

            if isinstance(val, (int, float, bool, type(None))):
                var_info["value"] = repr(val)
                
            elif isinstance(val, str):
                truncated = val[:max_str_len] + "..." if len(val) > max_str_len else val
                var_info["value"] = repr(truncated)
                
            elif isinstance(val, (list, tuple, set)):
                var_info["has_children"] = len(val) > 0
                var_info["value"] = f"{var_type} ({len(val)} items)"
                
                if depth < max_depth:
                    items = list(val)[:max_collection_len]
                    var_info["children"] = [
                        _inspect(str(i), item, depth + 1) for i, item in enumerate(items)
                    ]
                    if len(val) > max_collection_len:
                        var_info["children"].append({
                            "name": "...", 
                            "type": "", 
                            "value": f"{len(val) - max_collection_len} more items", 
                            "has_children": False
                        })
                        
            elif isinstance(val, dict):
                var_info["has_children"] = len(val) > 0
                var_info["value"] = f"dict ({len(val)} keys)"
                
                if depth < max_depth:
                    for i, (k, v) in enumerate(val.items()):
                        if i >= max_collection_len:
                            var_info["children"].append({
                                "name": "...", 
                                "type": "", 
                                "value": f"{len(val) - max_collection_len} more keys", 
                                "has_children": False
                            })
                            break
                        var_info["children"].append(_inspect(str(k), v, depth + 1))
                        
            # complex object fallback (classes ect..)
            else:
                try:
                    rep = repr(val)
                    var_info["value"] = rep[:max_str_len] + "..." if len(rep) > max_str_len else rep
                    
                    if hasattr(val, '__dict__') and depth < max_depth:
                        var_info["has_children"] = True
                        attrs = list(val.__dict__.items())[:max_collection_len]
                        var_info["children"] = [_inspect(k, v, depth + 1) for k, v in attrs]
                except Exception:
                    var_info["value"] = "<Unrepresentable Object>"

            return var_info

        return [_inspect(k, v, 0) for k, v in frame_vars.items()]

    def get_locals(self):
        return self.format_frame_vars(dict(self.local_variables))
