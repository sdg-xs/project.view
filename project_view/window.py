"""Composer panel for finding, saving, and reopening project inspections."""

from __future__ import annotations

import asyncio

import omni.ui as ui
from object_colors.discovery import property_label

from .records import IDENTITY_PROJECT_ID
from .views import DEFAULT_COLOR, ProjectViews


class ProjectViewWindow:
    def __init__(self, views: ProjectViews):
        self.views = views
        self.window = ui.Window("Project View", width=430, height=700)
        self.property_search = ui.SimpleStringModel("ProjectID")
        self.id_search = ui.SimpleStringModel("")
        self.name = ui.SimpleStringModel("")
        self.color = ui.SimpleStringModel(DEFAULT_COLOR)
        self.padding = ui.SimpleFloatModel(1.0)
        self.selected_id = None
        self.selected_record_id = None
        self._shown_generation = views.generation
        self._shown_content = None
        self._shown_source_id = None
        self._property_frame = None
        self._id_frame = None
        self._saved_frame = None
        self._status_label = None
        self._using_label = None
        self._tasks = set()
        views.add_listener(self._changed)
        self.window.frame.set_build_fn(self._build)
        self.property_search.add_value_changed_fn(lambda _: self._property_frame.rebuild() if self._property_frame else None)
        self.id_search.add_value_changed_fn(lambda _: self._id_frame.rebuild() if self._id_frame else None)
        self.window.frame.rebuild()

    def show(self):
        self.window.visible = True

    def destroy(self):
        self.views.remove_listener(self._changed)
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()
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
                self.views.status = str(error)
                self._changed(self.views)

        task.add_done_callback(finished)

    def _call(self, function, *args):
        try:
            function(*args)
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
            self.color.set_value(views.content.chosen_color)
            self.padding.set_value(views.content.padding_metres)
            self.selected_id = views.content.project_id
            if self.id_search.as_string.casefold() not in str(self.selected_id.value).casefold():
                self.id_search.set_value("")
            self._shown_content = views.content
        elif views.content is None:
            self._shown_content = None
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
        if self._using_label is not None:
            self._using_label.text = f"Using: {property_label(views.property_name)}"
        if self._property_frame is not None:
            self._property_frame.rebuild()
        if self._id_frame is not None:
            self._id_frame.rebuild()
        if self._saved_frame is not None:
            self._saved_frame.rebuild()

    def _build(self):
        with ui.ScrollingFrame():
            with ui.VStack(spacing=8, margin=12, height=0):
                ui.Label("Project View", height=28, style={"font_size": 20})
                self._status_label = ui.Label(self.views.status, word_wrap=True, height=54)
                ui.Separator(height=2)

                ui.Label("Project ID property", height=22)
                with ui.HStack(height=26):
                    ui.StringField(self.property_search, tooltip="Find a Project ID property")
                    ui.Button("Scan", width=65, clicked_fn=lambda: self._run(self.views.discover(self.views.property_name)))
                self._using_label = ui.Label(f"Using: {property_label(self.views.property_name)}",
                                             word_wrap=True, height=35)
                self._property_frame = ui.Frame(height=94)
                self._property_frame.set_build_fn(self._build_properties)

                ui.Label("Project ID", height=22)
                ui.StringField(self.id_search, tooltip="Filter discovered Project IDs")
                self._id_frame = ui.Frame(height=145)
                self._id_frame.set_build_fn(self._build_ids)
                with ui.HStack(height=27, spacing=5):
                    ui.Label("Padding (m)", width=100)
                    ui.FloatField(self.padding)
                    ui.Button("Preview", width=82, clicked_fn=self._preview)

                ui.Separator(height=2)
                ui.Label("Highlight", height=22)
                with ui.HStack(height=27, spacing=5):
                    ui.StringField(self.color, tooltip="#RRGGBB")
                    ui.Button("Apply color", width=95, clicked_fn=lambda: self._run(self.views.set_highlight(self.color.as_string)))
                    ui.Button("No highlight", width=105, clicked_fn=lambda: self._run(self.views.set_highlight(None)))
                with ui.HStack(height=27, spacing=5):
                    ui.Button("Refresh assets", clicked_fn=lambda: self._run(self.views.refresh()))
                    ui.Button("Refit section", clicked_fn=lambda: self._run(self.views.refit(self.padding.as_float)))
                    ui.Button("Exit view", clicked_fn=lambda: self._run(self.views.exit()))

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

    def _build_properties(self):
        needle = self.property_search.as_string.casefold()
        properties = [key for key in self.views.properties if needle in property_label(key).casefold()]
        with ui.ScrollingFrame():
            with ui.VStack(spacing=2, height=0):
                if not properties:
                    ui.Label("Click Scan to discover model properties.", word_wrap=True)
                for key in properties[:80]:
                    ui.Button(property_label(key), height=23, tooltip=key,
                              clicked_fn=lambda selected=key: self._select_property(selected))
                if len(properties) > 80:
                    ui.Label("Refine the property search to see more results.")

    def _select_property(self, key):
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
                    marker = "● " if choice.project_id == self.selected_id else ""
                    ui.Button(marker + choice.label, height=23,
                              clicked_fn=lambda selected=choice.project_id: self._select_id(selected))
                if len(choices) > 100:
                    ui.Label("Refine the ID search to see more results.")

    def _select_id(self, project_id):
        self.selected_id = project_id
        self._id_frame.rebuild()

    def _preview(self):
        if self.selected_id is None:
            self.views.status = "Select a Project ID first."
            self._changed(self.views)
            return
        self._run(self.views.preview(self.views.property_name, self.selected_id, self.padding.as_float))

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
