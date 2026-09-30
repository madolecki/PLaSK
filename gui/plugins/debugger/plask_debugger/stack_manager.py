import json

class StackManager:

    def __init__(self, dbg_path):
        self.ignored_vars = {}
        self.stack = []
        self.dbg_path = dbg_path

    def _frame_id(self, frame):
        return id(frame)

    def _should_show_frame(self, frame):
        if frame.f_code.co_filename.endswith(("bdb.py", "dbg.py")):
            return False
        return True

    def _filter_frame_locals(self, frame):

        def to_safe(value):
            try:
                json.dumps(value)
                return value
            except (TypeError, OverflowError):
                return {"__type__": type(value).__name__, "__repr__": repr(value)}

        def sanitize(obj):
            if isinstance(obj, dict) or hasattr(obj, 'items'):
                try:
                    return {str(k): sanitize(v) for k, v in obj.items()}
                except Exception:
                    pass 

            if isinstance(obj, (list, tuple, set)):
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
                        # Only grab a few attributes to avoid massive overhead
                        attrs = list(val.__dict__.items())[:max_collection_len]
                        var_info["children"] = [_inspect(k, v, depth + 1) for k, v in attrs]
                except Exception:
                    var_info["value"] = "<Unrepresentable Object>"

            return var_info

        return [_inspect(k, v, 0) for k, v in frame_vars.items()]

    def _frame_info(self, frame):
        local_vars = self._filter_frame_locals(frame)
        return {
            "id": self._frame_id(frame),
            "function": frame.f_code.co_name,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "locals": self.format_frame_vars(dict(local_vars)),
        }

    def rebuild_from_frame(self, frame, ignored_vars=None):
        new_stack = []
        f = frame
        self.ignored_vars = ignored_vars or {}

        while f is not None:
            # Stop tracing into debugger internals immediately
            if f.f_code.co_filename == self.dbg_path:
                break
                
            if self._should_show_frame(f):
                new_stack.append(self._frame_info(f))

            f = f.f_back

        new_stack.pop()
        self.stack = new_stack

    def get_stack(self):
        return self.stack
