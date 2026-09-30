"""Composer panel for finding, saving, and reopening project inspections."""

from __future__ import annotations

import asyncio

import omni.kit.app
import omni.ui as ui
from omni.ui import color as cl
from object_colors.discovery import property_label
from object_colors.scheme import PALETTE
from section_box.extension import get_runtime_state

from .records import IDENTITY_PROJECT_ID
from .views import ProjectViews


class ProjectViewWindow:
    def __init__(self, views: ProjectViews):
        self.views = views
        self.window = ui.Window("Project View", width=430, height=700)
        self.id_search = ui.SimpleStringModel("")
        self.name = ui.SimpleStringModel("")
        self.selected_id = None
        self.selected_record_id = None
        self._shown_generation = views.generation
        self._shown_content = None
        self._shown_source_id = None
        self._property_frame = None
        self._id_frame = None
        self._asset_status_frame = None
        self._section_frame = None
        self._show_box_model = None
        self._syncing_show_box = False
        self._section_state = get_runtime_state()
        if self._section_state is not None:
            self._section_state.add_listener(self._section_changed)
        self._saved_frame = None
        self._status_label = None
        self._palette_window = None
        self._palette_context = None
        self._tasks = set()
        self._pending_transparency = None
        self._transparency_task = None
        views.add_listener(self._changed)
        self.window.frame.set_build_fn(self._build)
        self.id_search.add_value_changed_fn(lambda _: self._id_frame.rebuild() if self._id_frame else None)
        self.window.frame.rebuild()

    def show(self):
        self.window.visible = True

    def destroy(self):
        self.views.remove_listener(self._changed)
        if self._section_state is not None:
            self._section_state.remove_listener(self._section_changed)
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()
        self._close_palette()
        self.window.destroy()

    def _run(self, coroutine):
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)

        def finished(done):
            self._tasks.discard(done)
            if done.cancelled():
                return
            error = done.exception()
            if error is not None:
                content = self.views.content
                self.selected_id = (content.project_id
                                    if content is not None and content.property_name == self.views.property_name else None)
                self.views.status = str(error)
                self._changed(self.views)

        task.add_done_callback(finished)
        return task

    def _call(self, function, *args, **kwargs):
        try:
            function(*args, **kwargs)
        except Exception as exc:
            self.views.status = str(exc)
            self._changed(self.views)

    def _changed(self, views):
        if self._shown_generation != views.generation:
            self.selected_id = None
            self.selected_record_id = None
            self._shown_generation = views.generation
            self._shown_content = None
            self._shown_source_id = None
        if views.content is not None and views.content is not self._shown_content:
            self.selected_id = views.content.project_id
            if self.id_search.as_string.casefold() not in str(self.selected_id.value).casefold():
                self.id_search.set_value("")
            self._shown_content = views.content
        elif views.content is None:
            self._shown_content = None
            if not views.busy:
                self.selected_id = None
        if views.source_id != self._shown_source_id:
            self._shown_source_id = views.source_id
            if views.source_id is not None:
                self.selected_record_id = views.source_id
                try:
                    self.name.set_value(self.views.store.get(views.source_id).name)
                except ValueError:
                    pass
        if self._status_label is not None:
            self._status_label.text = views.status
        if self._property_frame is not None:
            self._property_frame.rebuild()
        if self._id_frame is not None:
            self._id_frame.rebuild()
        if self._asset_status_frame is not None and not views.busy:
            self._asset_status_frame.rebuild()
        if self._section_frame is not None:
            self._section_frame.rebuild()
        if self._palette_window is not None and self._palette_context != self._status_context():
            self._close_palette()
        if self._saved_frame is not None:
            self._saved_frame.rebuild()

    def _build(self):
        with ui.ScrollingFrame():
            with ui.VStack(spacing=8, margin=12, height=0):
                ui.Label("Project View", height=28, style={"font_size": 20})
                self._status_label = ui.Label(self.views.status, word_wrap=True, height=54)
                ui.Separator(height=2)

                ui.Label("Project ID property", height=22)
                with ui.HStack(height=26, spacing=5):
                    self._property_frame = ui.Frame()
                    self._property_frame.set_build_fn(self._build_properties)
                    ui.Button("Scan", width=65, clicked_fn=lambda: self._run(self.views.discover(self.views.property_name)))

                ui.Label("Project ID", height=22)
                ui.StringField(self.id_search, tooltip="Filter discovered Project IDs")
                self._id_frame = ui.Frame(height=145)
                self._id_frame.set_build_fn(self._build_ids)

                ui.Separator(height=2)
                ui.Label("Asset Status", height=22)
                self._asset_status_frame = ui.Frame(height=0)
                self._asset_status_frame.set_build_fn(self._build_asset_status)
                self._section_frame = ui.Frame(height=88)
                self._section_frame.set_build_fn(self._build_section_controls)

                ui.Separator(height=2)
                ui.Label("Saved views", height=22)
                self._saved_frame = ui.Frame(height=150)
                self._saved_frame.set_build_fn(self._build_saved)
                ui.Label("View name", height=20)
                ui.StringField(self.name)
                with ui.HStack(height=27, spacing=5):
                    ui.Button("Save New", clicked_fn=lambda: self._call(self.views.save_new, self.name.as_string))
                    ui.Button("Update", clicked_fn=lambda: self._call(self.views.update))
                    ui.Button("Rename", clicked_fn=self._rename)
                    ui.Button("Delete", clicked_fn=self._delete)
                ui.Label("Use Composer Save (Save As for a new scene) to write view changes to disk.",
                         word_wrap=True, height=34)

    def _build_section_controls(self):
        with ui.VStack(spacing=5, height=0):
            section = get_runtime_state()
            with ui.HStack(height=24, spacing=8, enabled=self.views.content is not None and not self.views.busy):
                ui.Label("Show Box", width=0)
                model = ui.SimpleBoolModel(section.show_box if section is not None else False)
                self._show_box_model = model
                ui.CheckBox(model=model, width=24, identifier="project_view_show_box")
                model.add_value_changed_fn(self._set_show_box)
            with ui.HStack(height=27, spacing=5, enabled=self.views.content is not None and not self.views.busy):
                ui.Button("Save section", tooltip="Use this section box whenever you select this Project ID",
                          clicked_fn=lambda: self._call(self.views.save_section))
                ui.Button("Reset section", tooltip="Remove the saved section and fit the project with 1 metre of padding",
                          clicked_fn=lambda: self._run(self.views.reset_section()))
            ui.Button("Exit view", height=27, clicked_fn=lambda: self._run(self.views.exit()))

    def _section_changed(self, section):
        model = self._show_box_model
        if model is not None and model.as_bool != section.show_box:
            self._syncing_show_box = True
            try:
                model.set_value(section.show_box)
            finally:
                self._syncing_show_box = False

    def _set_show_box(self, model):
        if self._syncing_show_box or self.views.content is None or self.views.busy:
            return
        section = get_runtime_state()
        if section is not None and section.stage is self.views.stage:
            self._call(section.edit, show_box=model.as_bool)

    def _build_properties(self):
        properties = [key for key in self.views.properties
                      if "projectid" in "".join(char for char in property_label(key).casefold() if char.isalnum())]
        active = self.views.property_name
        if active not in properties:
            properties.insert(0, active)
        if IDENTITY_PROJECT_ID in properties:
            properties.remove(IDENTITY_PROJECT_ID)
            properties.insert(0, IDENTITY_PROJECT_ID)
        combo = ui.ComboBox(properties.index(active), *(property_label(key) for key in properties),
                            height=26, enabled=bool(self.views.properties), identifier="project_id_property",
                            tooltip="Choose the property containing the Project ID. Click Scan to discover properties.")
        combo.model.add_item_changed_fn(
            lambda model, _: self._select_property(properties[model.get_item_value_model().as_int]))

    def _select_property(self, key):
        if key == self.views.property_name:
            return
        self.selected_id = None
        self.id_search.set_value("")
        self._run(self.views.discover(key))

    def _build_ids(self):
        choices = self.views.filtered_choices(self.id_search.as_string)
        with ui.ScrollingFrame():
            with ui.VStack(spacing=2, height=0):
                if not choices:
                    ui.Label("No IDs in this search.", height=24)
                for choice in choices[:100]:
                    ui.Button(choice.label, height=23, selected=choice.project_id == self.selected_id,
                              style={"Button:selected": {"background_color": 0xFF805D36}},
                              clicked_fn=lambda selected=choice.project_id: self._select_id(selected))
                if len(choices) > 100:
                    ui.Label("Refine the ID search to see more results.")

    def _select_id(self, project_id):
        self.selected_id = project_id
        self._id_frame.rebuild()
        self._run(self.views.preview(self.views.property_name, project_id))

    def _build_asset_status(self):
        content = self.views.content
        with ui.VStack(spacing=4, height=0, enabled=not self.views.busy):
            if content is None:
                ui.Label("Select a Project ID to see its asset statuses.", word_wrap=True, height=34)
                return
            settings = content.asset_status
            active = settings.property_name if settings else ""
            properties = list(self.views.status_properties)
            if active and active not in properties:
                properties.insert(0, active)
            if not active:
                properties.insert(0, "")
            labels = [property_label(key) if key else "Choose an Asset Status property..." for key in properties]
            combo = ui.ComboBox(properties.index(active), *labels, height=26,
                                enabled=bool(self.views.status_properties), identifier="asset_status_property",
                                tooltip="Asset Status properties found in this project")
            combo.model.add_item_changed_fn(
                lambda model, _: self._select_status_property(properties[model.get_item_value_model().as_int]))
            coloring = settings.color_enabled if settings is not None else content.highlight_enabled
            with ui.HStack(height=26, spacing=5):
                ui.Button("Original", height=26, selected=not coloring,
                          style={"Button:selected": {"background_color": 0xFF805D36}},
                          tooltip="Show the project's original materials",
                          clicked_fn=lambda: self._run(self.views.set_status_coloring(False)))
                ui.Button("Color", height=26, selected=coloring,
                          style={"Button:selected": {"background_color": 0xFF805D36}},
                          tooltip="Color every status in this project using its chosen color",
                          clicked_fn=lambda: self._run(self.views.set_status_coloring(True)))
            groups = self.views.status_groups if active else ()
            if not groups:
                message = ("No Asset Status properties were found in this project." if not self.views.status_properties
                           else "Choose an Asset Status property to list its values." if not active
                           else "No status values are available for this property in the selected project.")
                ui.Label(message, word_wrap=True, height=34)
            else:
                with ui.ScrollingFrame(height=140):
                    with ui.VStack(spacing=4, height=0):
                        for group in groups:
                            with ui.HStack(height=26, spacing=6):
                                ui.Button(f"{group.label} ({len(group.objects)})", height=26,
                                          identifier="asset_status_value",
                                          selected=settings is not None and settings.selected_key == group.key,
                                          style={"Button:selected": {"background_color": 0xFF805D36}},
                                          clicked_fn=lambda key=group.key: self._run(self.views.select_status(key)))
                                percentage = dict(settings.transparencies).get(group.key, 0)
                                slider = ui.FloatSlider(model=ui.SimpleFloatModel(percentage), min=0, max=100,
                                                        width=112, height=24, format="%.0f%%",
                                                        identifier="asset_status_transparency",
                                                        tooltip=f"{group.label} transparency: 0% opaque, 100% transparent")
                                context = self._status_context()
                                slider.model.add_end_edit_fn(
                                    lambda model, key=group.key, captured=context:
                                    self._set_transparency(captured, key, round(model.as_float)))
                                target = 0 if percentage == 100 else 100
                                ui.Button(f"{target}%", width=38, height=24,
                                          identifier="asset_status_transparency_full",
                                          tooltip=(f"Set {group.label} to 0% and restore its geometry" if target == 0
                                                   else f"Set {group.label} to 100% and hide its geometry"),
                                          clicked_fn=lambda key=group.key, captured=context, value=target:
                                          self._set_transparency(captured, key, value))
                                color = cl(group.color)
                                ui.Button("", width=24, height=24, identifier="asset_status_color",
                                          tooltip=f"Change color for {group.label}",
                                          style={
                                              "Button": {"background_color": color, "border_radius": 12,
                                                         "border_width": 0, "padding": 12, "margin": 0},
                                              "Button:hovered": {"background_color": color},
                                              "Button:pressed": {"background_color": color},
                                          }, clicked_fn=lambda selected=group: self._open_palette(selected))

    def _select_status_property(self, key):
        content = self.views.content
        if key and content is not None and (content.asset_status is None or content.asset_status.property_name != key):
            self._run(self.views.set_status_property(key))

    def _set_transparency(self, context, key, percentage):
        if context != self._status_context():
            return
        self._pending_transparency = context, key, percentage
        if self._transparency_task is None or self._transparency_task.done():
            self._transparency_task = self._run(self._apply_transparency())

    async def _apply_transparency(self):
        while self._pending_transparency is not None:
            context, key, percentage = self._pending_transparency
            self._pending_transparency = None
            while self.views.busy and context == self._status_context():
                await omni.kit.app.get_app().next_update_async()
            if context != self._status_context():
                continue
            settings = self.views.content.asset_status
            if dict(settings.transparencies).get(key, 0) != percentage:
                await self.views.set_status_transparency(key, percentage)

    def _status_context(self):
        content = self.views.content
        if content is None or content.asset_status is None:
            return None
        return (self.views.generation, content.property_name, content.project_id,
                content.asset_status.property_name, self.views.source_id)

    def _close_palette(self):
        if self._palette_window is not None:
            window = self._palette_window
            window.visible = False
            self._palette_window = None
            self._run(self._destroy_palette(window))
        self._palette_context = None

    async def _destroy_palette(self, window):
        await omni.kit.app.get_app().next_update_async()
        window.destroy()

    def _open_palette(self, group):
        self._close_palette()
        context = self._status_context()
        if context is None:
            return
        self._palette_context = context
        self._palette_window = ui.Window("Asset Status color", width=350, height=225)
        with self._palette_window.frame:
            with ui.VStack(spacing=6, margin=10):
                ui.Label(group.label, height=24, elided_text=True)
                for row in range(5):
                    with ui.HStack(spacing=4, height=28):
                        for color in PALETTE[row * 8:(row + 1) * 8]:
                            ui.Button("\u25a0", height=28, tooltip=color, identifier="asset_status_palette_color",
                                      style={"background_color": cl(color), "color": cl(color)},
                                      clicked_fn=lambda chosen=color: self._choose_status_color(context, group.key, chosen))

    def _choose_status_color(self, context, key, color):
        self._close_palette()
        if (context != self._status_context() or self.views.busy
                or not any(group.key == key for group in self.views.status_groups)):
            return
        self._run(self.views.set_status_color(key, color))

    def _build_saved(self):
        try:
            records = self.views.saved_views()
        except Exception as exc:
            with ui.VStack(height=0):
                ui.Label(str(exc), word_wrap=True)
            return
        with ui.ScrollingFrame():
            with ui.VStack(spacing=2, height=0):
                if not records:
                    ui.Label("No views saved in this scene yet.")
                for record in records:
                    marker = "● " if record.id == self.selected_record_id else ""
                    with ui.HStack(height=25, spacing=4):
                        ui.Button(marker + record.name, clicked_fn=lambda selected=record: self._select_record(selected))
                        ui.Button("Open", width=55, clicked_fn=lambda selected=record.id: self._run(self.views.open(selected)))
                if self.views.store and self.views.store.unsupported:
                    ui.Label(f"{len(self.views.store.unsupported)} unsupported saved view records were left untouched.",
                             word_wrap=True, height=35)

    def _select_record(self, record):
        self.selected_record_id = record.id
        self.name.set_value(record.name)
        self._saved_frame.rebuild()

    def _rename(self):
        if self.selected_record_id is None:
            self.views.status = "Select a saved view to rename."
            self._changed(self.views)
        else:
            self._call(self.views.rename, self.selected_record_id, self.name.as_string)

    def _delete(self):
        if self.selected_record_id is None:
            self.views.status = "Select a saved view to delete."
            self._changed(self.views)
        else:
            self._call(self.views.delete, self.selected_record_id)
            self.selected_record_id = None
