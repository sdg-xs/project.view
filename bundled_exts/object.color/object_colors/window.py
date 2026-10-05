"""Composer-native panel with a searchable property selector and fixed swatches."""
from pathlib import Path

import omni.ui as ui

from .discovery import property_label
from .scheme import PALETTE


def swatch_color(color):
    if color is None:
        return 0xFF555555
    return 0xFF000000 | int(color[5:7], 16) << 16 | int(color[3:5], 16) << 8 | int(color[1:3], 16)


class ObjectColorsWindow:
    def __init__(self, controller):
        self.controller = controller
        self.window = ui.Window('Object Colors', width=440, height=690)
        self.search = ui.SimpleStringModel('')
        self.palette_window = None
        controller.listeners.append(self.update)
        self.window.frame.set_build_fn(self.build)
        self.search.add_value_changed_fn(lambda _: self.property_frame.rebuild())

    def update(self, rebuild=True):
        if rebuild:
            if self.palette_window:
                self.palette_window.visible = False
            self.window.frame.rebuild()
        elif hasattr(self, 'status_label'):
            self.status_label.text = self.controller.status

    def show(self):
        self.window.visible = True

    def build(self):
        controller = self.controller
        with ui.VStack(spacing=8, margin=12):
            ui.Label('Object Colors', height=25, style={'font_size': 20})
            ui.Label('Whole stage', height=18, style={'color': 0xFFAAAAAA})
            if controller.inspection_active:
                ui.Label('Project View owns the displayed colors. Scheme edits are saved and appear after Exit View.',
                         word_wrap=True, height=38, style={'color': 0xFF88BBFF})
            with ui.VStack(spacing=8, height=0, enabled=not controller.busy and controller.stage is not None):
                with ui.HStack(height=24):
                    enabled = ui.CheckBox(width=22)
                    enabled.model.set_value(controller.scheme.enabled)
                    enabled.model.add_value_changed_fn(lambda m: controller.edit(enabled=m.as_bool))
                    ui.Label('Enable colors')
                    ui.Button('Refresh', width=85, clicked_fn=controller.refresh)
                with ui.HStack(height=24):
                    ui.Label('Color by', width=78)
                    modes = ('Property', 'File', 'Model')
                    combo = ui.ComboBox(modes.index(controller.scheme.mode), *modes)
                    combo.model.add_item_changed_fn(
                        lambda m, _: controller.edit(mode=modes[m.get_item_value_model().as_int]))
                reason = controller.scan.unavailable_reason(controller.scheme.mode)
                if reason:
                    ui.Label(reason, word_wrap=True, height=34, style={'color': 0xFF88BBFF})
                if controller.scheme.mode == 'Property':
                    with ui.HStack(height=24):
                        ui.Image(str(Path(__file__).resolve().parent.parent / 'data/search.svg'),
                                 width=24, height=24, tooltip='Search properties')
                        ui.StringField(self.search, tooltip='Filter property names and categories')
                    self.property_frame = ui.Frame(height=0)
                    self.property_frame.set_build_fn(self._build_properties)
            ui.Separator(height=2)
            with ui.HStack(height=22):
                ui.Label('Value')
                ui.Label('Objects', width=62, alignment=ui.Alignment.RIGHT_CENTER)
                ui.Label('Color', width=58, alignment=ui.Alignment.CENTER)
            with ui.ScrollingFrame():
                with ui.VStack(spacing=4, height=0, enabled=not controller.busy):
                    for group in controller.groups:
                        with ui.HStack(height=26, spacing=6):
                            ui.Label(group.label, tooltip=group.key, elided_text=True)
                            ui.Label(str(len(group.objects)), width=56, alignment=ui.Alignment.RIGHT_CENTER)
                            with ui.HStack(width=58, height=24):
                                ui.Spacer()
                                color = swatch_color(group.color)
                                ui.Button('', width=24, height=24,
                                          style={
                                              'Button': {'background_color': color, 'border_radius': 12,
                                                         'border_width': 0, 'padding': 12, 'margin': 0},
                                              'Button:hovered': {'background_color': color},
                                              'Button:pressed': {'background_color': color},
                                          },
                                          tooltip='Color', clicked_fn=lambda g=group: self._palette(g))
                                ui.Spacer()
            self.status_label = ui.Label(controller.status, height=36, word_wrap=True)
            if controller.issues:
                notice_label = 'notice' if len(controller.issues) == 1 else 'notices'
                with ui.CollapsableFrame(f'{len(controller.issues)} {notice_label}', height=0, collapsed=True):
                    with ui.ScrollingFrame(height=110):
                        ui.Label('\n'.join(controller.issues), word_wrap=True, alignment=ui.Alignment.LEFT_TOP)
            ui.Label('Save the scene to retain its active color scheme.',
                     word_wrap=True, height=32, style={'color': 0xFFAAAAAA})

    def _build_properties(self):
        query = self.search.as_string.strip().casefold()
        keys = [k for k in self.controller.scan.properties if query in property_label(k).casefold()]
        active = self.controller.scheme.property_key
        if query:
            if not keys:
                ui.Label('No matching properties', height=26)
                return
            with ui.ScrollingFrame(height=min(len(keys), 6) * 28,
                                   horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF):
                with ui.VStack(spacing=2, height=0):
                    for key in keys:
                        ui.Button(property_label(key), height=26, tooltip=key,
                                  style={'Button.Label': {'alignment': ui.Alignment.LEFT_CENTER}},
                                  clicked_fn=lambda k=key: self._select_property(k))
            return
        if active and active not in keys:
            keys.insert(0, active)
        if not keys:
            ui.Label('No matching properties', height=26)
            return
        combo = ui.ComboBox(keys.index(active) if active in keys else 0, *(property_label(k) for k in keys), height=26)
        combo.model.add_item_changed_fn(lambda m, _: self._select_property(keys[m.get_item_value_model().as_int]))

    def _select_property(self, key):
        self.search.set_value('')
        if key != self.controller.scheme.property_key:
            self.controller.edit(property_key=key)

    def _palette(self, group):
        if self.palette_window:
            self.palette_window.destroy()
        self.palette_window = ui.Window('Choose color', width=350, height=260)
        generation = self.controller.generation
        criterion = self.controller.scheme.criterion
        with self.palette_window.frame:
            with ui.VStack(spacing=6, margin=10):
                ui.Label(group.label, height=24, elided_text=True)
                for row in range(5):
                    with ui.HStack(spacing=4, height=28):
                        for color in PALETTE[row * 8:(row + 1) * 8]:
                            ui.Button('\u25a0', height=28, style={'background_color': swatch_color(color), 'color': swatch_color(color)},
                                      clicked_fn=lambda c=color: self._choose(group.key, c, generation, criterion))
                ui.Button('No color', height=26, clicked_fn=lambda: self._choose(group.key, None, generation, criterion))

    def _choose(self, key, color, generation, criterion):
        if self.palette_window:
            self.palette_window.visible = False
        if (self.controller.busy or self.controller.generation != generation
                or self.controller.scheme.criterion != criterion):
            return
        self.controller.edit(color=(key, color))

    def close(self):
        self.controller.listeners.remove(self.update)
        if self.palette_window:
            self.palette_window.destroy()
        self.window.destroy()
