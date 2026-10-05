# Bundled runtime dependencies

These runtime snapshots ship with Project View so a fresh clone or source ZIP can run without unpublished changes from a separate checkout. Add this directory as a Kit extension search path alongside the directory containing `project.view`.

| Extension | Source | Snapshot |
| --- | --- | --- |
| `section.box` | [sdg-xs/usd-composer-section-box](https://github.com/sdg-xs/usd-composer-section-box) | Commit `027840955ea475baace052ff8661d375d5474e9e` |
| `object.color` | [sdgnemyno/usd-composer-object-colors](https://github.com/sdgnemyno/usd-composer-object-colors) | Commit `30ba284daf91934760bf8f88e19f4ccb3621e8c4` plus the local transparency implementation in `appearance.py`, `controller.py`, and `overrides.py` tested with Project View |

Each snapshot includes its extension configuration, Python runtime, data, and original README. Development graphs, test outputs, and Git history are excluded. The upstream Object Colors commit alone does not include the transparency API imported by this Project View version.
