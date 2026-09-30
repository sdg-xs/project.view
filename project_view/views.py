"""A named Project ID view coordinates the existing color and section owners."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import math
from typing import Callable

import omni.kit.app
import omni.kit.viewport.utility as viewport_utility
import omni.usd
from object_colors.discovery import property_label, scan_steps
from object_colors.appearance import Appearance
from object_colors.extension import get_controller
from object_colors.scheme import Group
from pxr import Gf, UsdGeom
from section_box.extension import get_runtime_state
from section_box.model import Face, SectionBox
from section_box.selection import classify_visible_paths, fit_box_to_paths

from .records import BoxRecord, IDENTITY_PROJECT_ID, ProjectId, SectionDefault, ViewContent, ViewRecord, ViewStore
from .statuses import StatusSettings, status_groups, status_properties, valid_color


DEFAULT_COLOR = "#E15759"


@dataclass(frozen=True)
class Choice:
    project_id: ProjectId
    count: int

    @property
    def label(self) -> str:
        suffix = "" if self.project_id.kind == "str" else f" ({self.project_id.kind})"
        return f"{self.project_id.value}{suffix} ({self.count})"


@dataclass(frozen=True)
class Membership:
    matching: tuple[str, ...] = ()
    visible: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    no_geometry: tuple[str, ...] = ()
    colored: int = 0
    color_issues: tuple[str, ...] = ()


class ProjectViews:
    """Panel-facing operations for one active Composer scene and viewport."""

    def __init__(self) -> None:
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.generation = 0
        self.store = self._new_store(self.stage) if self.stage else None
        self.properties: tuple[str, ...] = ()
        self.choices: tuple[Choice, ...] = ()
        self.status_properties: tuple[str, ...] = ()
        self.status_groups: tuple[Group, ...] = ()
        self._status_objects = ()
        self.property_name = IDENTITY_PROJECT_ID
        self.membership = Membership()
        self.content: ViewContent | None = None
        self.source_id: str | None = None
        self.status = "Choose a Project ID to preview."
        self.busy = False
        self._scan_result = None
        self._scope = None
        self._committed_assignments: dict[str, str | Appearance] = {}
        self._baseline = None
        self._session_viewport = None
        self._intent = 0
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[ProjectViews], None]] = []
        self._sub = self.context.get_stage_event_stream().create_subscription_to_pop(
            self._stage_event, name="project.view.stage"
        )
        self._viewport_exit_task = None
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="project.view.viewport"
        )

    def _on_update(self, event) -> None:
        if (self._session_viewport is not None
                and viewport_utility.get_active_viewport(usd_context_name=None) != self._session_viewport
                and (self._viewport_exit_task is None or self._viewport_exit_task.done())):
            self._viewport_exit_task = asyncio.ensure_future(self.exit())

    def add_listener(self, callback: Callable[[ProjectViews], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ProjectViews], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def filtered_choices(self, search: str) -> tuple[Choice, ...]:
        needle = search.casefold()
        return tuple(choice for choice in self.choices if needle in str(choice.project_id.value).casefold())

    @staticmethod
    def _choices_for_property(scan, property_name: str, search: str = "") -> tuple[Choice, ...]:
        counts: dict[ProjectId, int] = {}
        for obj in scan.objects:
            try:
                project_id = ProjectId.from_value(obj.properties.get(property_name))
            except ValueError:
                continue
            counts[project_id] = counts.get(project_id, 0) + 1
        needle = search.casefold()
        return tuple(
            Choice(key, count)
            for key, count in sorted(counts.items(), key=lambda item: (str(item[0].value).casefold(), item[0].kind))
            if needle in str(key.value).casefold()
        )

    def _notify(self) -> None:
        for callback in tuple(self._listeners):
            callback(self)

    def _new_store(self, stage):
        return ViewStore(stage, self.generation, lambda: self.generation, lambda: self.stage)

    def _stage_event(self, event) -> None:
        if event.type in (int(omni.usd.StageEventType.OPENED), int(omni.usd.StageEventType.CLOSING),
                          int(omni.usd.StageEventType.CLOSED)):
            self._intent += 1
            old_scope, self._scope = self._scope, None
            if old_scope is not None:
                asyncio.ensure_future(old_scope.close())
            self.stage = self.context.get_stage() if event.type == int(omni.usd.StageEventType.OPENED) else None
            self.generation += 1
            self.store = self._new_store(self.stage) if self.stage else None
            self.content = None
            self.source_id = None
            self._baseline = None
            self._session_viewport = None
            self._scan_result = None
            self.membership = Membership()
            self.status_properties = ()
            self.status_groups = ()
            self._status_objects = ()
            self._committed_assignments = {}
            self.properties = ()
            self.choices = ()
            self.status = "Choose a Project ID to preview." if self.stage else "Open a USD scene."
            self._notify()

    def _bound(self):
        stage = self.context.get_stage()
        section = get_runtime_state()
        colors = get_controller()
        viewport = viewport_utility.get_active_viewport(usd_context_name=None)
        if stage is None or section is None or colors is None or viewport is None:
            raise ValueError("Open a scene and enable Section Box and Object Colors.")
        section.sync_stage()
        if stage != self.stage or stage != section.stage or stage != colors.stage or stage != viewport.stage:
            raise ValueError("The active viewport and extensions must use the same USD scene.")
        if self._session_viewport is not None and viewport is not self._session_viewport:
            raise ValueError("Exit this view before switching to another viewport.")
        if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
            raise ValueError("This Project View version supports Z-up scenes.")
        scale = float(UsdGeom.GetStageMetersPerUnit(stage))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("This scene has invalid metres-per-unit metadata.")
        return stage, section, colors, viewport, scale

    @staticmethod
    def _require_clipping(stage, viewport, enabled: bool) -> None:
        if enabled:
            product = stage.GetPrimAtPath(viewport.render_product_path)
            if not product or not product.GetAttribute("omni:rtx:scene:sectionPlane:plane"):
                raise ValueError("The active viewport cannot display an enabled section box yet.")

    async def _scan(self, intent: int):
        stage, *_ = self._bound()
        steps = scan_steps(stage)
        try:
            while True:
                if intent != self._intent or stage != self.stage:
                    raise asyncio.CancelledError
                try:
                    next(steps)
                except StopIteration as done:
                    self._scan_result = done.value
                    self.properties = tuple(done.value.properties)
                    return done.value
                await omni.kit.app.get_app().next_update_async()
        finally:
            steps.close()

    async def discover(self, property_name: str = IDENTITY_PROJECT_ID, search: str = "") -> tuple[Choice, ...]:
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return ()
            self.busy = True
            self.status = "Discovering Project IDs..."
            self._notify()
            try:
                scan = await self._scan(intent)
                if property_name not in scan.properties:
                    self.choices = ()
                    self.status = f"Property not found: {property_label(property_name)}"
                    return ()
                self.property_name = property_name
                self.choices = self._choices_for_property(scan, property_name, search)
                self.status = f"{len(self.choices)} Project IDs found in {len(scan.objects)} objects."
                return self.choices
            except asyncio.CancelledError:
                return ()
            except Exception as exc:
                self.status = str(exc)
                raise
            finally:
                self.busy = False
                self._notify()

    @staticmethod
    def _box_record(section) -> BoxRecord:
        snapshot = section.snapshot
        matrix = snapshot.box.transform
        return BoxRecord(tuple(float(matrix[r, c]) for r in range(4) for c in range(4)),
                         tuple(float(v) for v in snapshot.box.size),
                         tuple(face.name for face in Face if face in snapshot.box.faces),
                         snapshot.enabled, snapshot.show_box)

    @staticmethod
    def _restore_box(section, record: BoxRecord) -> None:
        matrix = Gf.Matrix4d(*record.transform)
        box = SectionBox(transform=matrix, size=Gf.Vec3d(*record.size),
                         faces=frozenset(Face[name] for name in record.faces))
        section.apply(replace(section.snapshot, box=box, enabled=record.enabled,
                              show_box=record.show_box, saved_position_path=""))

    def _match(self, scan, property_name: str, project_id: ProjectId) -> Membership:
        paths = []
        for obj in scan.objects:
            value = obj.properties.get(property_name)
            try:
                if ProjectId.from_value(value) == project_id:
                    paths.append(obj.path)
            except ValueError:
                continue
        visible, hidden, no_geometry = classify_visible_paths(self.stage, paths)
        return Membership(tuple(paths), tuple(visible), tuple(hidden), tuple(no_geometry))

    @staticmethod
    def _padded_box(stage, visible: tuple[str, ...], padding_metres: float, scale: float) -> SectionBox | None:
        if not math.isfinite(padding_metres) or padding_metres < 0:
            raise ValueError("Padding must be a non-negative number of metres.")
        box = fit_box_to_paths(stage, visible)
        if box is None:
            return None
        addition = 2 * padding_metres / scale
        return replace(box, size=box.size + Gf.Vec3d(addition, addition, addition))

    @staticmethod
    def _status_state(scan, matching: Membership, settings: StatusSettings | None):
        paths = set(matching.matching)
        objects = [obj for obj in scan.objects if obj.path in paths]
        properties = status_properties(objects)
        if settings is None:
            settings = StatusSettings(properties[0] if properties else "")
        return properties, status_groups(objects, settings), tuple(objects)

    @staticmethod
    def _assignments(content: ViewContent, matching: Membership, groups: tuple[Group, ...]) -> dict[str, str | Appearance]:
        settings = content.asset_status
        if settings is None:
            color = content.highlight_color
            return {path: color for path in matching.matching if color is not None}
        transparencies = dict(settings.transparencies)
        return {path: Appearance(group.color if settings.color_enabled else None, transparencies.get(group.key, 0))
                for group in groups if settings.color_enabled or transparencies.get(group.key, 0)
                for path in group.objects}

    async def _paint(self, stage, matching: Membership, assignments: dict[str, str | Appearance]) -> Membership:
        acquired = self._scope is None
        if self._scope is None:
            self._scope = get_controller().begin_inspection(stage)
        scope = self._scope
        try:
            report = await scope.apply(assignments)
        except BaseException:
            if acquired:
                if self._scope is scope:
                    self._scope = None
                await asyncio.shield(scope.close())
            elif self._scope is scope:
                try:
                    await scope.apply(self._committed_assignments)
                except BaseException:
                    pass
            raise
        return replace(matching, colored=report.colored, color_issues=tuple(report.issues))

    async def _revert_paint(self, acquired: bool) -> None:
        if self._scope is None:
            return
        if acquired or self.content is None:
            scope, self._scope = self._scope, None
            await scope.close()
            return
        await self._scope.apply(self._committed_assignments)

    async def preview(self, property_name: str, project_id: ProjectId, padding_metres: float = 1.0) -> Membership:
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return self.membership
            self.busy = True
            self.status = "Finding the project area..."
            self._notify()
            try:
                stage, section, _, viewport, scale = self._bound()
                scan = await self._scan(intent)
                matching = self._match(scan, property_name, project_id)
                if not matching.matching:
                    raise ValueError("No assets match this Project ID.")
                saved_section = self.store.get_section(property_name, project_id)
                box = None
                if saved_section is not None:
                    if saved_section.up_axis != "Z" or not math.isclose(scale, saved_section.metres_per_unit, rel_tol=1e-9):
                        raise ValueError("Scene units or up axis changed since this project section was saved.")
                else:
                    if not matching.visible:
                        raise ValueError(f"{len(matching.matching)} assets match, but none has visible geometry to fit.")
                    box = self._padded_box(stage, matching.visible, padding_metres, scale)
                    if box is None:
                        raise ValueError("Matching assets have no geometry that can be fitted.")
                self._require_clipping(stage, viewport, True)
                original = section.snapshot
                was_new = self._scope is None
                properties, groups, objects = self._status_state(scan, matching, None)
                previous = self.content.asset_status if self.content is not None else None
                settings = (replace(previous, selected_key=None, color_enabled=True)
                            if previous is not None and previous.property_name in properties
                            else StatusSettings(properties[0] if properties else ""))
                groups = status_groups(objects, settings)
                content = ViewContent(property_name, project_id, self._box_record(section), False,
                                      DEFAULT_COLOR, padding_metres, scale, "Z", settings)
                assignments = self._assignments(content, matching, groups)
                matching = await self._paint(stage, matching, assignments)
                try:
                    if (intent != self._intent or stage != self.stage or section.snapshot != original
                            or viewport_utility.get_active_viewport(usd_context_name=None) != viewport):
                        raise asyncio.CancelledError("The scene or section changed during Preview.")
                    if saved_section is not None:
                        self._restore_box(section, replace(saved_section.box, enabled=True, show_box=True))
                    else:
                        section.apply(replace(original, box=box, enabled=True,
                                              show_box=True, saved_position_path=""))
                except BaseException:
                    await self._revert_paint(was_new)
                    raise
                if self._baseline is None:
                    self._baseline = original
                    self._session_viewport = viewport
                self.content = replace(content, box=self._box_record(section))
                self.property_name = property_name
                self.choices = self._choices_for_property(scan, property_name)
                self.source_id = None
                self.membership = matching
                self.status_properties, self.status_groups, self._status_objects = properties, groups, objects
                self._committed_assignments = assignments
                self.status = self._summary(matching)
                return matching
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = str(exc)
                raise
            finally:
                self.busy = False
                self._notify()

    def _summary(self, membership: Membership) -> str:
        return (f"{len(membership.matching)} matching assets; {len(membership.visible)} visible, "
                f"{len(membership.hidden)} hidden, {len(membership.no_geometry)} without usable geometry. "
                f"{membership.colored} colored. {len(membership.color_issues)} color notices.")

    async def open(self, view_id: str) -> Membership:
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return self.membership
            self.busy = True
            self.status = "Opening saved view..."
            self._notify()
            try:
                stage, section, _, viewport, scale = self._bound()
                record = self.store.get(view_id)
                content = record.content
                if content.up_axis != "Z" or not math.isclose(scale, content.metres_per_unit, rel_tol=1e-9):
                    raise ValueError("Scene units or up axis changed since this view was saved.")
                scan = await self._scan(intent)
                matching = self._match(scan, content.property_name, content.project_id)
                self._require_clipping(stage, viewport, content.box.enabled)
                original = section.snapshot
                was_new = self._scope is None
                properties, groups, objects = self._status_state(scan, matching, content.asset_status)
                assignments = self._assignments(content, matching, groups)
                matching = await self._paint(stage, matching, assignments)
                try:
                    if (intent != self._intent or stage != self.stage or section.snapshot != original
                            or viewport_utility.get_active_viewport(usd_context_name=None) != viewport):
                        raise asyncio.CancelledError("The scene or section changed during Open.")
                    self._restore_box(section, content.box)
                except BaseException:
                    await self._revert_paint(was_new)
                    raise
                if self._baseline is None:
                    self._baseline = original
                    self._session_viewport = viewport
                self.content = content
                self.property_name = content.property_name
                self.choices = self._choices_for_property(scan, content.property_name)
                self.source_id = view_id
                self.membership = matching
                self.status_properties, self.status_groups, self._status_objects = properties, groups, objects
                self._committed_assignments = assignments
                self.status = self._summary(matching)
                return matching
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = str(exc)
                raise
            finally:
                self.busy = False
                self._notify()

    async def refresh(self) -> Membership:
        if self.content is None:
            raise ValueError("Preview or open a project view first.")
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return self.membership
            if self.content is None:
                raise ValueError("Preview or open a project view first.")
            self.busy = True
            self.status = "Refreshing current project assets..."
            self._notify()
            try:
                stage, *_ = self._bound()
                scan = await self._scan(intent)
                matching = self._match(scan, self.content.property_name, self.content.project_id)
                was_new = self._scope is None
                properties, groups, objects = self._status_state(scan, matching, self.content.asset_status)
                assignments = self._assignments(self.content, matching, groups)
                matching = await self._paint(stage, matching, assignments)
                if intent != self._intent or stage != self.stage:
                    await self._revert_paint(was_new)
                    raise asyncio.CancelledError("The scene changed during Refresh.")
                self.membership = matching
                self.status_properties, self.status_groups, self._status_objects = properties, groups, objects
                self._committed_assignments = assignments
                self.status = self._summary(matching)
                return matching
            finally:
                self.busy = False
                self._notify()

    def save_section(self) -> SectionDefault:
        if self.busy:
            raise ValueError("Wait for the current project operation to finish before saving its section.")
        if self.content is None:
            raise ValueError("Preview or open a project view first.")
        _, section, _, _, scale = self._bound()
        record = SectionDefault(self.content.property_name, self.content.project_id,
                                self._box_record(section), scale)
        record = self.store.save_section(record)
        self.content = replace(self.content, box=record.box)
        self.status = f"Saved the default section for Project ID {record.project_id.value}. {self._save_hint()}"
        self._notify()
        return record

    async def reset_section(self) -> Membership:
        return await self._refit(1.0, reset_default=True)

    async def refit(self, padding_metres: float) -> Membership:
        return await self._refit(padding_metres, reset_default=False)

    async def _refit(self, padding_metres: float, *, reset_default: bool) -> Membership:
        if self.content is None:
            raise ValueError("Preview or open a project view first.")
        if not math.isfinite(padding_metres) or padding_metres < 0:
            raise ValueError("Padding must be a non-negative number of metres.")
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return self.membership
            if self.content is None:
                raise ValueError("Preview or open a project view first.")
            self.busy = True
            self.status = "Resetting the project section..." if reset_default else "Refitting the section box..."
            self._notify()
            try:
                stage, section, _, viewport, scale = self._bound()
                store = self.store
                if reset_default:
                    store._require_writable()
                    store.get_section(self.content.property_name, self.content.project_id)
                scan = await self._scan(intent)
                matching = self._match(scan, self.content.property_name, self.content.project_id)
                box = self._padded_box(stage, matching.visible, padding_metres, scale) if matching.visible else None
                if reset_default and box is None:
                    raise ValueError("Cannot reset this section: matching assets have no visible geometry to fit.")
                if box is not None:
                    self._require_clipping(stage, viewport, True)
                original = section.snapshot
                was_new = self._scope is None
                properties, groups, objects = self._status_state(scan, matching, self.content.asset_status)
                assignments = self._assignments(self.content, matching, groups)
                matching = await self._paint(stage, matching, assignments)
                applied_box = False
                try:
                    if (intent != self._intent or stage != self.stage or section.snapshot != original
                            or viewport_utility.get_active_viewport(usd_context_name=None) != viewport):
                        raise asyncio.CancelledError("The scene or section changed during Refit.")
                    if box is not None:
                        applied_box = True
                        section.apply(replace(original, box=box, enabled=True,
                                              show_box=True, saved_position_path=""))
                    if reset_default:
                        store.reset_section(self.content.property_name, self.content.project_id)
                except BaseException:
                    try:
                        if applied_box and stage == self.stage and section.stage == stage:
                            section.apply(original)
                    finally:
                        await self._revert_paint(was_new)
                    raise
                self.content = replace(self.content, box=self._box_record(section), padding_metres=padding_metres)
                self.membership = matching
                self.status_properties, self.status_groups, self._status_objects = properties, groups, objects
                self._committed_assignments = assignments
                self.status = self._summary(matching) + (" Box unchanged: no visible geometry to fit." if box is None else "")
                if reset_default:
                    self.status += f" Reset to the automatic section with 1 m padding. {self._save_hint()}"
                return matching
            finally:
                self.busy = False
                self._notify()

    def _status_context(self):
        content = self.content
        if content is None:
            return None
        return (self.generation, content.property_name, content.project_id,
                content.asset_status.property_name if content.asset_status is not None else None)

    async def _update_status(self, change: Callable[[StatusSettings], StatusSettings]) -> Membership:
        requested = self._status_context()
        if requested is None:
            raise ValueError("Preview or open a project view first.")
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent or requested != self._status_context():
                return self.membership
            self.busy = True
            self.status = "Updating Asset Status..."
            self._notify()
            try:
                stage, _, _, viewport, _ = self._bound()
                settings = self.content.asset_status or StatusSettings(
                    self.status_properties[0] if self.status_properties else "",
                    color_enabled=self.content.highlight_enabled)
                settings = change(settings)
                groups = status_groups(self._status_objects, settings)
                content = replace(self.content, asset_status=settings, highlight_enabled=False)
                assignments = self._assignments(content, self.membership, groups)
                was_new = self._scope is None
                matching = await self._paint(stage, self.membership, assignments)
                if (intent != self._intent or stage != self.stage or requested != self._status_context()
                        or viewport_utility.get_active_viewport(usd_context_name=None) != viewport):
                    await self._revert_paint(was_new)
                    raise asyncio.CancelledError("The project changed during the Asset Status update.")
                self.content = content
                self.status_groups = groups
                self.membership = matching
                self._committed_assignments = assignments
                self.status = self._summary(matching)
                return matching
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = str(exc)
                raise
            finally:
                self.busy = False
                self._notify()

    async def set_status_property(self, property_name: str) -> Membership:
        def choose(settings):
            if property_name not in self.status_properties:
                raise ValueError("Choose an Asset Status property available in this project.")
            return (replace(settings, selected_key=None) if property_name == settings.property_name
                    else StatusSettings(property_name, color_enabled=settings.color_enabled))

        return await self._update_status(choose)

    async def select_status(self, key: str | None) -> Membership:
        def choose(settings):
            if key is not None and not any(group.key == key for group in self.status_groups):
                raise ValueError("Choose an Asset Status value available in this project.")
            return replace(settings, selected_key=key)

        return await self._update_status(choose)

    async def set_status_coloring(self, enabled: bool) -> Membership:
        def choose(settings):
            if type(enabled) is not bool:
                raise ValueError("Choose Color or Original for Asset Status display.")
            return replace(settings, color_enabled=enabled, selected_key=None)

        return await self._update_status(choose)

    async def set_status_color(self, key: str, color: str) -> Membership:
        def choose(settings):
            if not any(group.key == key for group in self.status_groups):
                raise ValueError("Choose an Asset Status value available in this project.")
            if not valid_color(color):
                raise ValueError("Choose a six-digit color such as #E15759.")
            colors = dict(settings.colors)
            colors[key] = color.upper()
            return replace(settings, colors=tuple(sorted(colors.items())))

        return await self._update_status(choose)

    async def set_status_transparency(self, key: str, percentage: int) -> Membership:
        def choose(settings):
            if not any(group.key == key for group in self.status_groups):
                raise ValueError("Choose an Asset Status value available in this project.")
            if type(percentage) is not int or not 0 <= percentage <= 100:
                raise ValueError("Transparency must be a whole percentage from 0 to 100.")
            values = dict(settings.transparencies)
            values[key] = percentage
            return replace(settings, transparencies=tuple(sorted(values.items())))

        return await self._update_status(choose)

    async def set_highlight(self, color: str | None) -> Membership:
        if self.content is None:
            raise ValueError("Preview or open a project view first.")
        chosen = self.content.chosen_color if color is None else color
        if len(chosen) != 7 or chosen[0] != "#" or any(c not in "0123456789ABCDEFabcdef" for c in chosen[1:]):
            raise ValueError("Choose a six-digit color such as #E15759.")
        self._intent += 1
        intent = self._intent
        async with self._lock:
            if intent != self._intent:
                return self.membership
            if self.content is None:
                raise ValueError("Preview or open a project view first.")
            stage, *_ = self._bound()
            was_new = self._scope is None
            assignments = {path: color for path in self.membership.matching if color is not None}
            matching = await self._paint(stage, self.membership, assignments)
            if intent != self._intent or stage != self.stage:
                await self._revert_paint(was_new)
                raise asyncio.CancelledError("The scene changed during highlight update.")
            self.content = replace(self.content, highlight_enabled=color is not None, chosen_color=chosen,
                                   asset_status=None)
            self.membership = matching
            self.status_groups = status_groups(self._status_objects, StatusSettings(
                self.status_properties[0] if self.status_properties else ""))
            self._committed_assignments = assignments
            self.status = self._summary(matching)
            self._notify()
            return matching

    def _capture(self) -> ViewContent:
        if self.content is None:
            raise ValueError("Preview or open a project view first.")
        _, section, _, _, _ = self._bound()
        captured = replace(self.content, box=self._box_record(section))
        return ViewContent.from_data(captured.to_data())

    def saved_views(self) -> tuple[ViewRecord, ...]:
        return self.store.list() if self.store else ()

    def _save_hint(self) -> str:
        if self.stage.GetRootLayer().anonymous:
            return "Use Composer Save As to write this new scene to disk."
        return "Use Composer Save to write it to disk."

    def save_new(self, name: str) -> ViewRecord:
        record = self.store.new(name, self._capture())
        self.content = record.content
        self.source_id = record.id
        self.status = f"Saved view '{record.name}' in the scene. {self._save_hint()}"
        self._notify()
        return record

    def update(self) -> ViewRecord:
        if self.source_id is None:
            raise ValueError("Save this new view before updating it.")
        record = self.store.update(self.source_id, self._capture())
        self.content = record.content
        self.status = f"Updated '{record.name}' in the scene. {self._save_hint()}"
        self._notify()
        return record

    def rename(self, view_id: str, name: str) -> ViewRecord:
        record = self.store.rename(view_id, name)
        self.status = f"Renamed view to '{record.name}'. {self._save_hint()}"
        self._notify()
        return record

    def delete(self, view_id: str) -> None:
        self.store.delete(view_id)
        if self.source_id == view_id:
            self.source_id = None
        self.status = f"Deleted the saved view in the scene. {self._save_hint()}"
        self._notify()

    async def exit(self) -> None:
        self._intent += 1
        async with self._lock:
            scope, self._scope = self._scope, None
            try:
                if scope is not None:
                    await scope.close()
            finally:
                try:
                    if self._baseline is not None:
                        section = get_runtime_state()
                        if section is not None and section.stage is self.stage:
                            section.apply(self._baseline)
                finally:
                    self._baseline = None
                    self._session_viewport = None
                    self.content = None
                    self.source_id = None
                    self.membership = Membership()
                    self.status_properties = ()
                    self.status_groups = ()
                    self._status_objects = ()
                    self._committed_assignments = {}
                    self.status = "Project view closed."
                    self._notify()

    def destroy(self) -> None:
        self._intent += 1
        self._sub = None
        self._update_sub = None
        scope, self._scope = self._scope, None
        try:
            if self._baseline is not None:
                section = get_runtime_state()
                if section is not None and section.stage is self.stage:
                    section.apply(self._baseline)
        finally:
            self._baseline = None
            self._session_viewport = None
            self.content = None
            self.membership = Membership()
            self.status_properties = ()
            self.status_groups = ()
            self._status_objects = ()
            self._committed_assignments = {}
            self._listeners.clear()
            if scope is not None:
                asyncio.ensure_future(scope.close())
