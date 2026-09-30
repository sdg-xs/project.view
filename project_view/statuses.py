"""Asset Status settings and groups scoped to a project's discovered assets."""

from dataclasses import dataclass
import json

from object_colors.discovery import property_label
from object_colors.scheme import Group, Scheme, value_key


def valid_color(color: object) -> bool:
    return (isinstance(color, str) and len(color) == 7 and color[0] == "#"
            and all(char in "0123456789abcdefABCDEF" for char in color[1:]))


def _valid_key(key: object) -> bool:
    if not isinstance(key, str) or ":" not in key:
        return False
    try:
        value = json.loads(key.split(":", 1)[1])
    except (TypeError, ValueError):
        return False
    return value_key(value) == key and not (isinstance(value, str) and not value.strip())


@dataclass(frozen=True)
class StatusSettings:
    property_name: str = ""
    selected_key: str | None = None
    colors: tuple[tuple[str, str], ...] = ()
    color_enabled: bool = True
    transparencies: tuple[tuple[str, int], ...] = ()

    @classmethod
    def from_data(cls, data: dict, version: int = 4) -> "StatusSettings":
        fields = {"property_name", "selected_key", "colors"}
        if version >= 3:
            fields.add("color_enabled")
        if version >= 4:
            fields.add("transparencies")
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("Invalid Asset Status settings.")
        property_name, selected, colors = data["property_name"], data["selected_key"], data["colors"]
        enabled = data["color_enabled"] if version >= 3 else selected is not None
        if type(enabled) is not bool:
            raise ValueError("Invalid Asset Status color mode.")
        if not isinstance(property_name, str) or (selected is not None and not _valid_key(selected)):
            raise ValueError("Invalid Asset Status property or value.")
        if not isinstance(colors, list) or any(
            not isinstance(pair, list) or len(pair) != 2 or not _valid_key(pair[0]) or not valid_color(pair[1])
            for pair in colors
        ):
            raise ValueError("Invalid Asset Status colors.")
        if len({pair[0] for pair in colors}) != len(colors):
            raise ValueError("Duplicate Asset Status color values.")
        transparencies = data["transparencies"] if version >= 4 else []
        if not isinstance(transparencies, list) or any(
            not isinstance(pair, list) or len(pair) != 2 or not _valid_key(pair[0])
            or type(pair[1]) is not int or not 0 <= pair[1] <= 100 for pair in transparencies
        ):
            raise ValueError("Invalid Asset Status transparency percentages.")
        if len({pair[0] for pair in transparencies}) != len(transparencies):
            raise ValueError("Duplicate Asset Status transparency values.")
        if not property_name and (selected is not None or colors or transparencies):
            raise ValueError("Asset Status values require a property.")
        return cls(property_name, selected, tuple((key, color.upper()) for key, color in colors), enabled,
                   tuple((key, value) for key, value in transparencies))

    def to_data(self) -> dict:
        return {"property_name": self.property_name, "selected_key": self.selected_key,
                "colors": [list(pair) for pair in self.colors], "color_enabled": self.color_enabled,
                "transparencies": [list(pair) for pair in self.transparencies]}


def status_properties(objects) -> tuple[str, ...]:
    return tuple(sorted({key for obj in objects for key in obj.properties
                         if "assetstatus" in "".join(
                             char for char in property_label(key).casefold() if char.isalnum())}))


def status_groups(objects, settings: StatusSettings) -> tuple[Group, ...]:
    scheme = Scheme(property_key=settings.property_name)
    overrides = dict(settings.colors)
    members: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for obj in objects:
        value = obj.properties.get(settings.property_name)
        key = value_key(value)
        if key == "missing" or (isinstance(value, str) and not value.strip()):
            continue
        members.setdefault(key, []).append(obj.path)
        labels[key] = str(value) + ("" if isinstance(value, str) else f" ({type(value).__name__})")
    return tuple(Group(key, labels[key], tuple(members[key]), overrides.get(key, scheme.color(key)))
                 for key in sorted(members, key=lambda key: (labels[key].casefold(), key)))
