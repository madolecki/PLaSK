import json


class _ClassInstance:
    __slots__ = ("class_name", "attrs", "repr_str")

    def __init__(self, class_name, attrs, repr_str):
        self.class_name = class_name
        self.attrs = attrs
        self.repr_str = repr_str


class _ClassRef:
    __slots__ = ("class_name", "repr_str")

    def __init__(self, class_name, repr_str):
        self.class_name = class_name
        self.repr_str = repr_str


_SKIP = object()


class LocalsManager:

    def __init__(self):
        self.ignored_vars = None
        self.show_classes = False
        self.local_variables = {}

    def update_locals(self, frame, ignored_vars=None, show_classes=False):
        self.ignored_vars = ignored_vars
        self.show_classes = show_classes
        self.local_variables = self._filter_frame_locals(frame)

    def _filter_frame_locals(self, frame):

        def to_safe(value):
            try:
                json.dumps(value)
                return value
            except (TypeError, OverflowError):
                return {"__type__": type(value).__name__, "__repr__": repr(value)}

        def sanitize(obj, _seen=None):
            if _seen is None:
                _seen = set()

            if isinstance(obj, (int, float, bool, str, type(None))):
                return obj

            if isinstance(obj, type):
                if not self.show_classes:
                    return _SKIP
                return _ClassRef(class_name=obj.__name__, repr_str=repr(obj))

            obj_id = id(obj)
            if obj_id in _seen:
                return {"__type__": type(obj).__name__, "__repr__": "<circular reference>"}
            _seen = _seen | {obj_id}

            if isinstance(obj, dict) or hasattr(obj, 'items'):
                try:
                    sanitized_items = ((str(k), sanitize(v, _seen)) for k, v in obj.items())
                    return {k: v for k, v in sanitized_items if v is not _SKIP}
                except Exception:
                    pass

            if isinstance(obj, (list, tuple, set)):
                return [v for v in (sanitize(item, _seen) for item in obj) if v is not _SKIP]

            if hasattr(obj, '__dict__'):
                try:
                    sanitized_attrs = ((str(k), sanitize(v, _seen)) for k, v in vars(obj).items())
                    attrs = {k: v for k, v in sanitized_attrs if v is not _SKIP}
                    return _ClassInstance(
                        class_name=type(obj).__name__,
                        attrs=attrs,
                        repr_str=repr(obj),
                    )
                except Exception:
                    pass

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

            elif isinstance(val, _ClassInstance):
                var_info["type"] = val.class_name
                var_info["has_children"] = len(val.attrs) > 0
                var_info["value"] = (
                    val.repr_str[:max_str_len] + "..."
                    if len(val.repr_str) > max_str_len
                    else val.repr_str
                )

                if depth < max_depth:
                    attr_items = list(val.attrs.items())[:max_collection_len]
                    var_info["children"] = [
                        _inspect(k, v, depth + 1) for k, v in attr_items
                    ]
                    if len(val.attrs) > max_collection_len:
                        var_info["children"].append({
                            "name": "...",
                            "type": "",
                            "value": f"{len(val.attrs) - max_collection_len} more attributes",
                            "has_children": False
                        })

            elif isinstance(val, _ClassRef):
                var_info["type"] = "class"
                var_info["has_children"] = False
                var_info["value"] = (
                    val.repr_str[:max_str_len] + "..."
                    if len(val.repr_str) > max_str_len
                    else val.repr_str
                )

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
