"""Exercise named project views in a private headless Kit process."""

import asyncio
import gc
import json
from pathlib import Path
import sys
import traceback

import omni.kit.app
import omni.kit.renderer_capture
import omni.kit.undo
import omni.kit.ui_test as ui_test
import omni.kit.viewport.utility as viewport_utility
import omni.usd
import omni.ui as ui
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

from object_colors.discovery import property_label
from object_colors.extension import get_controller
from object_colors.scheme import value_key
from project_view.records import DATA, IDENTITY_PROJECT_ID, ProjectId, ViewRecord
from project_view.views import ProjectViews
from project_view.window import ProjectViewWindow
from section_box.extension import get_runtime_state
from section_box.model import SectionBox
from section_box.window import SectionBoxWindow


APP = omni.kit.app.get_app()
OUTPUT = Path(__file__).resolve().parent.parent / "verification"
SCENE = OUTPUT / "project-view-fixture.usda"
SCENE_CM = OUTPUT / "project-view-centimetres.usda"
SCENE_SECTIONS = OUTPUT / "project-view-sections.usda"
PROJECT = ProjectId.from_value("P-01514")
OTHER = ProjectId.from_value("P-02000")
CM_PROJECT = ProjectId.from_value("CM-WORK")
INVISIBLE = ProjectId.from_value("INVISIBLE")
ORIGINAL = "/World/Looks/Original"
SAME_PROJECT = ("/World/North", "/World/South", "/World/Hidden")
ALT_PROPERTY = "custom:alternateProjectId"
ASSET_STATUS = "custom:Asset_Status"
ALT_STATUS = "custom:AlternateAssetStatus"
OUTSIDE_STATUS = "custom:OtherAssetStatus"


async def frames(count=5):
    for _ in range(count):
        await APP.next_update_async()


async def colors_settled():
    controller = get_controller()
    assert controller is not None, "Object Colors did not start"
    await frames(2)
    if controller.task:
        await asyncio.wait_for(asyncio.shield(controller.task), 60)
    await frames(3)
    assert not controller.busy, controller.status
    assert not controller.status.startswith("Could not"), controller.status
    return controller


def source_material(stage):
    material = UsdShade.Material.Define(stage, ORIGINAL)
    shader = UsdShade.Shader.Define(stage, ORIGINAL + "/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.45, 0.5, 0.55))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def asset(stage, path, project_id, x, material, *, hidden=False, status=None):
    root = UsdGeom.Xform.Define(stage, path)
    root.AddTranslateOp().Set(Gf.Vec3d(x, 0, 0))
    if project_id is not None:
        root.GetPrim().CreateAttribute(IDENTITY_PROJECT_ID, Sdf.ValueTypeNames.String, custom=True).Set(project_id)
    if status is not None:
        root.GetPrim().CreateAttribute(ASSET_STATUS, Sdf.ValueTypeNames.String, custom=True).Set(status)
    cube = UsdGeom.Cube.Define(stage, path + "/Shape")
    cube.CreateSizeAttr(2.0)
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(material)
    if hidden:
        UsdGeom.Imageable(root).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    return root


def make_scene(output_path=SCENE):
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    material = source_material(stage)
    north = asset(stage, "/World/North", PROJECT.value, 0, material, status="Installed")
    north.GetPrim().CreateAttribute(ALT_STATUS, Sdf.ValueTypeNames.String, custom=True).Set("Checked")
    asset(stage, "/World/South", PROJECT.value, 5, material, status="Planned")
    asset(stage, "/World/Hidden", PROJECT.value, 100, material, hidden=True, status="Installed")
    other = asset(stage, "/World/Other", OTHER.value, 15, material, status="Installed")
    other.GetPrim().CreateAttribute(ALT_PROPERTY, Sdf.ValueTypeNames.String, custom=True).Set(PROJECT.value)
    other.GetPrim().CreateAttribute(OUTSIDE_STATUS, Sdf.ValueTypeNames.String, custom=True).Set("Outside only")
    asset(stage, "/World/Surroundings", None, -12, material, status="Unassigned area")
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 30))
    stage.GetRootLayer().Export(str(output_path))


def make_centimetre_scene():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    UsdGeom.Xform.Define(stage, "/World")
    material = source_material(stage)
    asset(stage, "/World/CmWest", CM_PROJECT.value, 0, material)
    asset(stage, "/World/CmEast", CM_PROJECT.value, 500, material)
    asset(stage, "/World/CmHidden", CM_PROJECT.value, 100000, material, hidden=True)
    asset(stage, "/World/OnlyHidden", INVISIBLE.value, -100000, material, hidden=True)
    for index in range(105):
        asset(stage, f"/World/Bulk{index:03d}", f"BULK-{index:03d}", 1000 + index * 5, material)
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 3000))
    stage.GetRootLayer().Export(str(SCENE_CM))


def material_path(stage, path):
    material, _ = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(path + "/Shape")).ComputeBoundMaterial()
    return str(material.GetPath()) if material else ""


def expect_material(stage, path, expected):
    actual = material_path(stage, path)
    assert actual == expected, (path, actual, expected)


def expect_box_bounds(box, low, high, tolerance=0.02):
    corners = box.corners()
    actual_low = tuple(min(point[index] for point in corners) for index in range(3))
    actual_high = tuple(max(point[index] for point in corners) for index in range(3))
    assert all(abs(actual_low[i] - low[i]) < tolerance for i in range(3)), (actual_low, low)
    assert all(abs(actual_high[i] - high[i]) < tolerance for i in range(3)), (actual_high, high)


def expect_camera(viewport, path):
    assert str(viewport.camera_path) == path, (viewport.camera_path, path)


def expect_raises(callback, message):
    try:
        callback()
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f"Expected ValueError containing {message!r}")


def panel_widgets(window_name="Project View"):
    pending = [ui.Workspace.get_window(window_name).frame]
    while pending:
        widget = pending.pop()
        yield widget
        pending.extend(ui.Inspector.get_children(widget))


def panel_button(text):
    matches = [widget for widget in panel_widgets() if isinstance(widget, ui.Button) and widget.text == text]
    assert len(matches) == 1, (text, len(matches))
    return matches[0]


def property_combo(identifier):
    matches = [widget for widget in panel_widgets()
               if isinstance(widget, ui.ComboBox) and widget.identifier == identifier]
    assert len(matches) == 1, (identifier, len(matches))
    return matches[0]


def property_labels(combo):
    return [combo.model.get_item_value_model(item).as_string for item in combo.model.get_item_children()]


def select_property(identifier, key):
    combo = property_combo(identifier)
    combo.model.get_item_value_model().set_value(property_labels(combo).index(property_label(key)))


def palette_button(color):
    matches = [widget for widget in panel_widgets("Asset Status color")
               if isinstance(widget, ui.Button) and widget.tooltip == color]
    assert len(matches) == 1, (color, len(matches))
    return matches[0]


def open_status_palette(label):
    matches = [widget for widget in panel_widgets()
               if isinstance(widget, ui.Button) and widget.identifier == "asset_status_color"
               and widget.tooltip == "Change color for " + label]
    assert len(matches) == 1, (label, len(matches))
    assert matches[0].text == "", "The color circle must not depend on a font glyph"
    matches[0].call_clicked_fn()


async def panel_until(predicate, message):
    for _ in range(300):
        await frames(1)
        if predicate():
            await frames(3)
            return
    labels = [widget.text for widget in panel_widgets() if isinstance(widget, ui.Label)]
    raise AssertionError(f"{message}: {labels}")


def status_slider(label):
    return next(widget for widget in panel_widgets() if isinstance(widget, ui.FloatSlider)
                and widget.identifier == "asset_status_transparency" and widget.tooltip.startswith(label + " transparency:"))


async def set_slider(label, percentage):
    slider = status_slider(label)
    x = slider.screen_position_x + 1 + (slider.computed_width - 2) * percentage / 100
    y = slider.screen_position_y + slider.computed_height / 2
    await ui_test.emulate_mouse_move_and_click(ui_test.Vec2(x, y))


def opacity(stage, path):
    material = UsdShade.Material.Get(stage, material_path(stage, path))
    value = material.ComputeSurfaceSource()[0].GetInput("opacity")
    return value.Get() if value else 1.0


async def verify_panel(stage, section, controller, viewport, checks):
    original_section = section.snapshot
    paths = SAME_PROJECT + ("/World/Other",)
    original_bindings = {path: material_path(stage, path) for path in paths}
    original_root = stage.GetRootLayer().ExportToString()
    context = omni.usd.get_context()
    original_selection = context.get_selection().get_selected_prim_paths()
    original_camera = str(viewport.camera_path)
    highlight = controller.overrides.material_root + "/C59A14F"
    widgets = list(panel_widgets())
    assert not any(isinstance(widget, ui.FloatField) for widget in widgets), "Padding still has an editor"
    assert not any(isinstance(widget, ui.Button) and widget.text == "Preview" for widget in widgets), (
        "The separate Preview button is still present"
    )
    assert len([widget for widget in widgets if isinstance(widget, ui.StringField)]) == 2, (
        "Expected only ID search and view name fields"
    )
    assert not any(isinstance(widget, ui.Button) and widget.text == "Apply color" for widget in widgets)
    combo = property_combo("project_id_property")
    assert property_labels(combo)[combo.model.get_item_value_model().as_int] == property_label(IDENTITY_PROJECT_ID)
    panel_button("Scan").call_clicked_fn()
    await panel_until(
        lambda: property_label(ALT_PROPERTY) in property_labels(property_combo("project_id_property")),
        "Scan did not discover the alternate Project ID property",
    )
    select_property("project_id_property", ALT_PROPERTY)
    await panel_until(
        lambda: any(isinstance(widget, ui.Button) and widget.text == "P-01514 (1)" for widget in panel_widgets()),
        "Changing the dropdown did not refresh Project IDs",
    )
    panel_button("P-01514 (1)").call_clicked_fn()
    await panel_until(
        lambda: section.enabled and controller.inspection_active
        and panel_button("P-01514 (1)").selected and not controller.busy,
        "Clicking a Project ID did not activate clipping",
    )
    expect_box_bounds(section.box, (13, -2, -2), (17, 2, 2))
    assert section.show_box and panel_button("P-01514 (1)").selected
    show_box = next(widget for widget in panel_widgets()
                    if isinstance(widget, ui.CheckBox) and widget.identifier == "project_view_show_box")
    standalone = next(window for window in gc.get_objects()
                      if isinstance(window, SectionBoxWindow) and window._state is section)
    standalone_show_box = standalone._show_checkbox
    assert standalone_show_box is not None
    assert show_box.model.as_bool
    fitted_box = section.box
    show_box.model.set_value(False)
    assert not section.show_box and not standalone_show_box.model.as_bool
    assert section.enabled and section.box == fitted_box
    standalone_show_box.model.set_value(True)
    assert show_box.model.as_bool and section.show_box and section.box == fitted_box
    assert panel_button("Color").selected
    assert material_path(stage, "/World/Other") != ORIGINAL
    for path in SAME_PROJECT:
        expect_material(stage, path, ORIGINAL)
    checks.append("property dropdown refreshes IDs and clicking an ID fits its assets with 1 m padding and automatically enables status colors")
    checks.append("Show Box in Project View hides the overlay without disabling clipping and stays synced with Section Box")

    async def exit_panel():
        panel_button("Exit view").call_clicked_fn()
        await panel_until(
            lambda: not controller.inspection_active and section.snapshot == original_section,
            "Exit view did not restore the original section and release colors",
        )
        await colors_settled()
        for path, binding in original_bindings.items():
            expect_material(stage, path, binding)
        assert not any(isinstance(widget, ui.Button) and widget.selected
                       and (widget.text.startswith("P-") or widget.identifier == "asset_status_value")
                       for widget in panel_widgets()), (
            "Exit view left a Project ID highlighted"
        )

    await exit_panel()
    select_property("project_id_property", IDENTITY_PROJECT_ID)
    await panel_until(
        lambda: any(isinstance(widget, ui.Button) and widget.text == "P-01514 (3)" for widget in panel_widgets()),
        "Returning to Identity Data did not restore its Project IDs",
    )
    project_button = panel_button("P-01514 (3)")
    other_button = panel_button("P-02000 (1)")
    for button in (project_button, other_button, project_button, other_button, project_button):
        button.call_clicked_fn()
    await panel_until(
        lambda: section.enabled and controller.inspection_active
        and abs(max(point[0] for point in section.box.corners()) - 7) < 0.02
        and panel_button("P-01514 (3)").selected and not controller.busy,
        "Rapid Project ID clicks did not preview the final requested ID",
    )
    expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
    assert material_path(stage, "/World/North") != ORIGINAL
    for path in ("/World/South", "/World/Hidden", "/World/Other"):
        expect_material(stage, path, ORIGINAL)
    assert panel_button("P-01514 (3)").selected
    assert not panel_button("P-02000 (1)").selected

    await panel_until(
        lambda: any(isinstance(widget, ui.ComboBox) and widget.identifier == "asset_status_property"
                    for widget in panel_widgets()),
        "Project preview did not offer Asset Status properties",
    )
    labels = set(property_labels(property_combo("asset_status_property")))
    assert labels == {property_label(ASSET_STATUS), property_label(ALT_STATUS)}, labels
    select_property("asset_status_property", ASSET_STATUS)
    await panel_until(
        lambda: any(isinstance(widget, ui.Button) and widget.text == "Installed (2)"
                    for widget in panel_widgets()),
        "Asset Status property did not list the selected project's values",
    )
    status_buttons = [widget for widget in panel_widgets()
                      if isinstance(widget, ui.Button) and widget.identifier == "asset_status_value"]
    assert {widget.text for widget in status_buttons} == {"Installed (2)", "Planned (1)"}
    assert not any(widget.selected for widget in status_buttons)
    assert panel_button("Color").selected and not panel_button("Original").selected
    combo = property_combo("asset_status_property")
    for text in ("Original", "Color"):
        button = panel_button(text)
        assert combo.screen_position_y + combo.computed_height <= button.screen_position_y + 1
        assert button.screen_position_y + button.computed_height <= min(
            widget.screen_position_y for widget in status_buttons) + 1
    assert not any(isinstance(widget, ui.Button) and widget.text == "No highlight" for widget in panel_widgets())
    assert all(material_path(stage, path) != ORIGINAL for path in SAME_PROJECT)
    status_section = section.snapshot
    planned_color = material_path(stage, "/World/South")
    panel_button("Installed (2)").call_clicked_fn()
    await panel_until(
        lambda: panel_button("Installed (2)").selected and material_path(stage, "/World/North") != ORIGINAL,
        "Clicking an Asset Status did not highlight its members",
    )
    expect_material(stage, "/World/Hidden", material_path(stage, "/World/North"))
    expect_material(stage, "/World/South", planned_color)
    expect_material(stage, "/World/Other", ORIGINAL)

    open_status_palette("Installed")
    await frames(3)
    capture = omni.kit.renderer_capture.acquire_renderer_capture_interface()
    capture.capture_next_frame_swapchain(str(OUTPUT / "data" / "asset-status-palette.png"))
    await frames(5)
    capture.wait_async_capture()
    palette_sizes = [(widget.computed_width, widget.computed_height)
                     for widget in panel_widgets("Asset Status color")
                     if isinstance(widget, ui.Button) and widget.identifier == "asset_status_palette_color"]
    assert len(palette_sizes) == 40, palette_sizes
    assert all(width >= 24 and height >= 24 for width, height in palette_sizes), palette_sizes
    color_button = palette_button("#59A14F")
    await ui_test.emulate_mouse_move_and_click(ui_test.Vec2(
        color_button.screen_position_x + color_button.computed_width / 2,
        color_button.screen_position_y + color_button.computed_height / 2))
    await panel_until(
        lambda: material_path(stage, "/World/North") == highlight,
        "The active status color circle did not change its members' color",
    )
    open_status_palette("Planned")
    await frames(3)
    palette_button("#F28E2B").call_clicked_fn()
    await frames(10)
    assert panel_button("Installed (2)").selected and not panel_button("Planned (1)").selected
    expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
    expect_material(stage, "/World/North", highlight)
    panel_button("Planned (1)").call_clicked_fn()
    await panel_until(
        lambda: material_path(stage, "/World/South") == controller.overrides.material_root + "/CF28E2B"
        and panel_button("Planned (1)").selected,
        "Selecting another status did not use its configured color",
    )
    for path in ("/World/North", "/World/Hidden"):
        expect_material(stage, path, highlight)
    expect_material(stage, "/World/Other", ORIGINAL)
    assert not panel_button("Installed (2)").selected
    assert section.snapshot == status_section, "Status or palette changes moved the section box"
    checks.append("Asset Status properties and values are project-scoped; all statuses stay colored when a row is clicked and circles edit each status without moving the section")

    panel_button("Original").call_clicked_fn()
    await panel_until(
        lambda: material_path(stage, "/World/South") == ORIGINAL and panel_button("Original").selected,
        "Original did not clear status colors",
    )
    panel_button("Installed (2)").call_clicked_fn()
    await frames(8)
    open_status_palette("Installed")
    await frames(3)
    palette_button("#4E79A7").call_clicked_fn()
    await frames(8)
    for path in paths:
        expect_material(stage, path, ORIGINAL)
    assert panel_button("Original").selected
    highlight = controller.overrides.material_root + "/C4E79A7"
    panel_button("Color").call_clicked_fn()
    await panel_until(lambda: material_path(stage, "/World/North") == highlight, "Color did not restore status colors")
    expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
    assert section.snapshot == status_section
    checks.append("Original and Color are between the status dropdown and list; Original survives row and palette edits and Color restores every status")

    for label, text in (("Installed", "Installed (2)"), ("Planned", "Planned (1)")):
        slider = status_slider(label)
        button = panel_button(text)
        full = next(widget for widget in panel_widgets() if widget.identifier == "asset_status_transparency_full"
                    and widget.tooltip.startswith("Set " + label + " to 100%"))
        circle = next(widget for widget in panel_widgets() if widget.identifier == "asset_status_color"
                      and widget.tooltip == "Change color for " + label)
        assert button.screen_position_x + button.computed_width <= slider.screen_position_x + 1
        assert slider.screen_position_x + slider.computed_width <= full.screen_position_x + 1
        assert full.screen_position_x + full.computed_width <= circle.screen_position_x + 1
        assert slider.model.as_int == 0 and full.text == "100%"
    await set_slider("Installed", 50)
    await panel_until(lambda: opacity(stage, "/World/North") == .5, "Slider did not change Color transparency")
    assert opacity(stage, "/World/South") == 1.0
    panel = next(widget for widget in gc.get_objects()
                 if isinstance(widget, ProjectViewWindow)
                 and widget.window is ui.Workspace.get_window("Project View"))
    status_context = panel._status_context()
    panel._set_transparency(status_context, value_key("Installed"), 25)
    await frames(1)
    assert panel.views.busy, "The first transparency update did not start"
    panel._set_transparency(status_context, value_key("Installed"), 75)
    await panel_until(lambda: opacity(stage, "/World/North") == .25 and
                      status_slider("Installed").model.as_int == 75,
                      "A later slider adjustment was lost while the scene updated")
    await set_slider("Installed", 50)
    await panel_until(lambda: opacity(stage, "/World/North") == .5,
                      "Slider did not settle on the final percentage")
    panel_button("Original").call_clicked_fn()
    await panel_until(lambda: panel_button("Original").selected and opacity(stage, "/World/North") == .5,
                      "Original mode lost transparency")
    copied = UsdShade.Material.Get(stage, material_path(stage, "/World/North")).ComputeSurfaceSource()[0]
    assert copied.GetInput("diffuseColor").Get() == Gf.Vec3f(.45, .5, .55)
    assert UsdGeom.Imageable(stage.GetPrimAtPath("/World/North")).ComputeVisibility() == UsdGeom.Tokens.inherited
    full = next(widget for widget in panel_widgets() if widget.identifier == "asset_status_transparency_full"
                and widget.tooltip.startswith("Set Installed to 100%"))
    full.call_clicked_fn()
    await panel_until(lambda: UsdGeom.Imageable(stage.GetPrimAtPath("/World/North")).ComputeVisibility()
                      == UsdGeom.Tokens.invisible, "100% did not hide the group")
    assert status_slider("Installed").model.as_int == 100
    restore = next(widget for widget in panel_widgets() if widget.identifier == "asset_status_transparency_full"
                   and widget.tooltip.startswith("Set Installed to 0%"))
    assert restore.text == "0%"
    assert next(widget for widget in panel_widgets() if widget.identifier == "asset_status_transparency_full"
                and widget.tooltip.startswith("Set Planned to 100%")).text == "100%"
    assert UsdGeom.Imageable(stage.GetPrimAtPath("/World/South")).ComputeVisibility() == UsdGeom.Tokens.inherited
    assert opacity(stage, "/World/South") == 1.0 and material_path(stage, "/World/Other") == ORIGINAL
    assert section.snapshot == status_section and str(viewport.camera_path) == original_camera
    capture.capture_next_frame_swapchain(str(OUTPUT / "data" / "asset-status-transparency.png"))
    await frames(5)
    capture.wait_async_capture()
    restore.call_clicked_fn()
    await panel_until(lambda: material_path(stage, "/World/North") == ORIGINAL and
                      UsdGeom.Imageable(stage.GetPrimAtPath("/World/North")).ComputeVisibility()
                      == UsdGeom.Tokens.inherited and status_slider("Installed").model.as_int == 0 and
                      any(widget.identifier == "asset_status_transparency_full" and widget.text == "100%"
                          and widget.tooltip.startswith("Set Installed to 100%") for widget in panel_widgets()),
                      "0% button did not restore originals and reset its label")
    panel_button("Color").call_clicked_fn()
    await panel_until(lambda: material_path(stage, "/World/North") == highlight, "Color did not restore after transparency")
    checks.append("each status button switches between 100% hide and 0% restore, updates its slider, and leaves other statuses and the section unchanged")

    active_section = section.snapshot
    active_bindings = {path: material_path(stage, path) for path in paths}
    session = stage.GetSessionLayer()
    assert not session.GetAttributeAtPath("/World/Other.visibility")
    try:
        with Usd.EditContext(stage, session):
            UsdGeom.Imageable(stage.GetPrimAtPath("/World/Other")).CreateVisibilityAttr(UsdGeom.Tokens.invisible)
        panel_button("P-02000 (1)").call_clicked_fn()
        await panel_until(
            lambda: any(isinstance(widget, ui.Label) and "none has visible geometry" in widget.text
                        for widget in panel_widgets()),
            "Previewing an entirely hidden ID did not report the failure",
        )
        assert panel_button("P-01514 (3)").selected, "Failed preview deselected the active project"
        assert not panel_button("P-02000 (1)").selected, "Failed preview left its ID highlighted"
        assert section.snapshot == active_section, "Failed preview changed the active section"
        for path, binding in active_bindings.items():
            expect_material(stage, path, binding)
        checks.append("a failed automatic preview retains the active ID selection, section and highlights")
    finally:
        with Usd.EditContext(stage, session):
            stage.GetPrimAtPath("/World/Other").RemoveProperty("visibility")

    panel_button("Original").call_clicked_fn()
    await panel_until(
        lambda: panel_button("Original").selected and material_path(stage, "/World/North") == ORIGINAL,
        "Original did not clear colors before switching projects",
    )
    open_status_palette("Installed")
    await frames(3)
    stale_color = palette_button("#59A14F")
    panel_button("P-02000 (1)").call_clicked_fn()
    await panel_until(
        lambda: panel_button("P-02000 (1)").selected
        and abs(max(point[0] for point in section.box.corners()) - 17) < 0.02
        and material_path(stage, "/World/North") == ORIGINAL,
        "Switching project retained the previous status highlight",
    )
    labels = set(property_labels(property_combo("asset_status_property")))
    assert labels == {property_label(ASSET_STATUS), property_label(OUTSIDE_STATUS)}, labels
    assert not any(widget.selected for widget in panel_widgets()
                   if isinstance(widget, ui.Button) and widget.identifier == "asset_status_value")
    other_color = material_path(stage, "/World/Other")
    assert other_color != ORIGINAL and panel_button("Color").selected
    stale_color.call_clicked_fn()
    await frames(10)
    for path in SAME_PROJECT:
        expect_material(stage, path, ORIGINAL)
    expect_material(stage, "/World/Other", other_color)
    checks.append("project changes clear the status selection, color the new project's statuses, recompute properties, and reject stale palette callbacks")

    await exit_panel()
    assert stage.GetRootLayer().ExportToString() == original_root, "Panel preview authored the model"
    assert context.get_selection().get_selected_prim_paths() == original_selection
    expect_camera(viewport, original_camera)
    checks.append("rapid ID clicks leave the final ID active and Exit restores prior section and colors without changing model, selection or camera")


async def verify_section_defaults(views, checks):
    make_scene(SCENE_SECTIONS)
    context = omni.usd.get_context()

    async def reopen():
        await context.close_stage_async()
        await context.open_stage_async(str(SCENE_SECTIONS))
        await frames(30)
        await colors_settled()
        section = get_runtime_state()
        section.sync_stage()
        viewport_utility.get_active_viewport().camera_path = "/World/ReviewCamera"
        return context.get_stage(), section

    stage, section = await reopen()
    panel_button("Scan").call_clicked_fn()
    await panel_until(lambda: any(isinstance(w, ui.Button) and w.text == "P-01514 (3)"
                                 for w in panel_widgets()), "Section fixture IDs were not discovered")
    panel_button("P-01514 (3)").call_clicked_fn()
    await panel_until(lambda: section.enabled and panel_button("Save section").enabled,
                      "Project preview did not enable Save section")
    buttons = {text: panel_button(text) for text in ("Save section", "Reset section", "Exit view")}
    assert not any(isinstance(w, ui.Button) and w.text in ("Refit section", "Refresh assets")
                   for w in panel_widgets())
    assert abs(buttons["Save section"].screen_position_y - buttons["Reset section"].screen_position_y) < 1
    assert buttons["Exit view"].screen_position_y >= (buttons["Save section"].screen_position_y
                                                       + buttons["Save section"].computed_height)
    assert buttons["Exit view"].computed_width >= (buttons["Save section"].computed_width
                                                   + buttons["Reset section"].computed_width)
    first = SectionBox(size=Gf.Vec3d(11, 8, 6)).with_z_rotation(31).translated(Gf.Vec3d(24, -6, 3))
    section.edit(box=first)
    panel_button("Original").call_clicked_fn()
    await panel_until(lambda: panel_button("Original").selected, "Original mode did not activate")
    panel_button("Save section").call_clicked_fn()
    await frames(5)
    assert panel_button("Original").selected and section.box == first
    panel_button("P-02000 (1)").call_clicked_fn()
    await panel_until(lambda: abs(max(p[0] for p in section.box.corners()) - 17) < 0.02,
                      "Another project inherited the saved section")
    panel_button("P-01514 (3)").call_clicked_fn()
    await panel_until(lambda: section.box == first, "Clicking the project did not restore its saved section")
    assert panel_button("Color").selected
    panel_button("Original").call_clicked_fn()
    await panel_until(lambda: panel_button("Original").selected, "Original mode did not reactivate")
    panel_button("Reset section").call_clicked_fn()
    await panel_until(lambda: abs(max(p[0] for p in section.box.corners()) - 7) < 0.02,
                      "Reset did not fit the project")
    expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
    assert panel_button("Original").selected
    panel_button("P-02000 (1)").call_clicked_fn()
    await panel_until(lambda: abs(max(p[0] for p in section.box.corners()) - 17) < 0.02, "Other project did not fit")
    panel_button("P-01514 (3)").call_clicked_fn()
    await panel_until(lambda: abs(max(p[0] for p in section.box.corners()) - 7) < 0.02,
                      "A reset project restored its removed default")
    panel_button("Exit view").call_clicked_fn()
    await panel_until(lambda: not get_controller().inspection_active, "Section UI inspection did not exit")
    await colors_settled()
    checks.append("Save and Reset sit above full-width Exit; UI Save restores rotated geometry on project click and Reset returns future clicks to 1 m fitting without changing color mode")

    await views.preview(IDENTITY_PROJECT_ID, PROJECT)
    section.edit(box=first)
    views.save_section()
    second = SectionBox(size=Gf.Vec3d(7, 12, 9)).with_z_rotation(-22).translated(Gf.Vec3d(-18, 9, 4))
    section.edit(box=second)
    views.save_section()
    assert views.saved_views() == (), "Section defaults appeared as named views"
    await views.preview(ALT_PROPERTY, PROJECT)
    expect_box_bounds(section.box, (13, -2, -2), (17, 2, 2))
    views.save_section()
    await views.preview(IDENTITY_PROJECT_ID, PROJECT)
    assert section.box == second, "Saving another property changed this project's default"
    named = views.save_new("Independent named view")
    await views.exit()
    stage.GetRootLayer().Save()
    stage, section = await reopen()
    await views.preview(IDENTITY_PROJECT_ID, PROJECT)
    assert section.box == second, "Scene reopen lost the overwritten section geometry"
    assert len(views.saved_views()) == 1 and views.store.get(named.id).content == named.content
    root = stage.GetRootLayer()
    root.SetPermissionToEdit(False)
    try:
        expect_raises(views.save_section, "read-only")
        try:
            await views.reset_section()
        except ValueError as error:
            assert "read-only" in str(error), str(error)
        else:
            raise AssertionError("Read-only Reset was accepted")
        assert section.box == second
    finally:
        root.SetPermissionToEdit(True)
    saved_default = views.store.get_section(IDENTITY_PROJECT_ID, PROJECT)
    session = stage.GetSessionLayer()
    with Usd.EditContext(stage, session):
        for path in SAME_PROJECT[:2]:
            UsdGeom.Imageable(stage.GetPrimAtPath(path)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    try:
        try:
            await views.reset_section()
        except ValueError as error:
            assert "visible" in str(error), str(error)
        else:
            raise AssertionError("Reset accepted a project with no visible geometry")
        assert section.box == second and views.store.get_section(IDENTITY_PROJECT_ID, PROJECT) == saved_default
    finally:
        with Usd.EditContext(stage, session):
            for path in SAME_PROJECT[:2]:
                stage.GetPrimAtPath(path).RemoveProperty("visibility")
    await views.set_status_coloring(False)
    settings = views.content.asset_status
    await views.reset_section()
    expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
    assert views.content.asset_status == settings
    assert views.store.get_section(IDENTITY_PROJECT_ID, PROJECT) is None
    assert views.store.get(named.id).content == named.content
    await views.exit()
    root.Save()
    stage, section = await reopen()
    await views.preview(IDENTITY_PROJECT_ID, PROJECT)
    expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
    assert views.store.get_section(ALT_PROPERTY, PROJECT) is not None
    await views.open(named.id)
    assert section.box == second, "Reset changed the independent named view"
    await views.exit()
    checks.append("section overwrite and Reset survive scene Save/reopen, isolate project properties, leave named views intact, and refuse read-only or invisible-project Reset without losing the saved section")


async def verify():
    OUTPUT.mkdir(exist_ok=True)
    checks = []
    views = None
    try:
        assert Path(sys.modules[ProjectViews.__module__].__file__).resolve().parent.parent == OUTPUT.parent, (
            "Kit loaded a different Project View checkout", sys.modules[ProjectViews.__module__].__file__
        )
        assert ui.Workspace.get_window("Project View") is not None, (
            "Project View extension was enabled but its panel did not start"
        )
        checks.append("Project View extension starts and creates its Window panel")
        make_scene()
        context = omni.usd.get_context()
        await context.open_stage_async(str(SCENE))
        await frames(30)
        stage = context.get_stage()
        controller = await colors_settled()
        section = get_runtime_state()
        assert section is not None, "Section Box did not start"
        section.sync_stage()
        assert section.stage is stage and controller.stage is stage
        viewport = viewport_utility.get_active_viewport()
        assert viewport is not None and viewport.stage is stage
        viewport.camera_path = "/World/ReviewCamera"
        camera_path = str(viewport.camera_path)
        assert camera_path == "/World/ReviewCamera"
        baseline = SectionBox(size=Gf.Vec3d(8, 10, 12)).translated(Gf.Vec3d(-5, 3, 2))
        section.edit(box=baseline, enabled=False, show_box=False)
        original_section = section.snapshot
        controller.edit(property_key=IDENTITY_PROJECT_ID, enabled=True,
                        color=('str:"P-02000"', "#4E79A7"))
        await colors_settled()
        expect_material(stage, "/World/Other", controller.overrides.material_root + "/C4E79A7")
        prior_bindings = {path: material_path(stage, path) for path in SAME_PROJECT + ("/World/Other",)}
        root_before_preview = stage.GetRootLayer().ExportToString()
        selected = ["/World/Other"]
        context.get_selection().set_selected_prim_paths(selected, False)

        await verify_panel(stage, section, controller, viewport, checks)

        views = ProjectViews()
        choices = await views.discover(IDENTITY_PROJECT_ID)
        assert {(choice.project_id, choice.count) for choice in choices} == {(PROJECT, 3), (OTHER, 1)}, choices
        assert ALT_PROPERTY in views.properties
        assert [(choice.project_id, choice.count) for choice in await views.discover(ALT_PROPERTY)] == [(PROJECT, 1)]
        membership = await views.preview(IDENTITY_PROJECT_ID, PROJECT)
        assert set(membership.matching) == set(SAME_PROJECT), membership
        assert set(membership.visible) == set(SAME_PROJECT[:2]), membership
        assert membership.hidden == ("/World/Hidden",), membership
        assert membership.colored == 1 and not membership.color_issues, membership
        assert section.enabled and section.show_box
        expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
        assert material_path(stage, "/World/North") != ORIGINAL
        for path in ("/World/South", "/World/Hidden", "/World/Other", "/World/Surroundings"):
            expect_material(stage, path, ORIGINAL)
        assert context.get_selection().get_selected_prim_paths() == selected
        assert stage.GetRootLayer().ExportToString() == root_before_preview, "Preview authored the model"
        expect_camera(viewport, camera_path)
        checks.append("exact Identity Data ID discovers placed assets; hidden geometry is excluded from the 1 m fit")
        checks.append("Preview clips the project and colors its first available status property while preserving outside materials, selection, model and camera")

        assert set(views.status_properties) == {ASSET_STATUS, ALT_STATUS}, views.status_properties
        await views.set_status_property(ASSET_STATUS)
        assert {(group.key, len(group.objects)) for group in views.status_groups} == {
            (value_key("Installed"), 2), (value_key("Planned"), 1)
        }
        await views.set_status_color(value_key("Installed"), "#59A14F")
        await views.set_status_color(value_key("Planned"), "#F28E2B")
        assert views.content.asset_status.selected_key is None
        assert views.content.asset_status.color_enabled and views.membership.colored == 3
        await views.select_status(value_key("Installed"))
        assert views.membership.colored == 3
        for path in ("/World/North", "/World/Hidden"):
            expect_material(stage, path, controller.overrides.material_root + "/C59A14F")
        expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
        for path in ("/World/Other", "/World/Surroundings"):
            expect_material(stage, path, ORIGINAL)
        await views.set_status_coloring(False)
        assert views.membership.colored == 0
        await views.set_status_property(ALT_STATUS)
        assert not views.content.asset_status.color_enabled and views.membership.colored == 0
        await views.set_status_property(ASSET_STATUS)
        await views.select_status(value_key("Planned"))
        await views.set_status_color(value_key("Planned"), "#59A14F")
        assert views.membership.colored == 0 and not views.content.asset_status.color_enabled
        for path in SAME_PROJECT:
            expect_material(stage, path, ORIGINAL)
        await views.set_highlight("#E15759")

        await views.set_highlight(None)
        assert views.content.highlight_color is None and views.content.chosen_color == "#E15759"
        for path in SAME_PROJECT + ("/World/Other",):
            expect_material(stage, path, ORIGINAL)
        await views.set_highlight("#E15759")
        expect_material(stage, "/World/North", controller.overrides.material_root + "/CE15759")
        expect_camera(viewport, camera_path)
        checks.append("legacy highlight clearing reveals original materials and re-enabling uses the chosen color")

        north = views.save_new("Level 2 north")
        saved_north = north.content
        section.edit(box=section.box.translated(Gf.Vec3d(10, 0, 0)))
        south = views.save_new("Level 2 south")
        assert north.id != south.id and north.content.box != south.content.box
        renamed = views.rename(north.id, "Level 2 north installation")
        assert renamed.id == north.id and renamed.content == saved_north
        expect_raises(lambda: views.rename(south.id, "LEVEL 2 NORTH INSTALLATION"), "already uses")
        await views.set_highlight("#59A14F")
        updated = views.update()
        assert updated.id == south.id and updated.content.highlight_color == "#59A14F"
        assert views.store.get(north.id).content == saved_north
        views.delete(north.id)
        assert {record.id for record in views.saved_views()} == {south.id}
        omni.kit.undo.undo()
        assert {record.id for record in views.saved_views()} == {north.id, south.id}
        assert views.store.get(north.id).name == "Level 2 north installation"
        omni.kit.undo.redo()
        assert {record.id for record in views.saved_views()} == {south.id}
        omni.kit.undo.undo()
        assert {record.id for record in views.saved_views()} == {north.id, south.id}
        expect_camera(viewport, camera_path)
        checks.append("multiple views, rename, update, duplicate-name refusal, and delete undo/redo retain independent records")

        root = stage.GetRootLayer()
        root.SetPermissionToEdit(False)
        try:
            expect_raises(lambda: views.save_new("Read-only refusal"), "read-only")
        finally:
            root.SetPermissionToEdit(True)
        assert {record.id for record in views.saved_views()} == {north.id, south.id}
        checks.append("a read-only scene refuses a new saved record")

        legacy = views.store.get(north.id).to_data()
        legacy["version"] = 1
        legacy["content"].pop("asset_status", None)
        loaded_legacy = ViewRecord.from_data(legacy)
        assert loaded_legacy.content.asset_status is None
        assert loaded_legacy.content.highlight_color == "#E15759"
        stage.GetPrimAtPath(f"/__ProjectViews/View_{north.id}").GetAttribute(DATA).Set(json.dumps(legacy))

        await views.set_status_property(ASSET_STATUS)
        await views.set_status_color(value_key("Installed"), "#59A14F")
        await views.set_status_color(value_key("Planned"), "#F28E2B")
        await views.set_status_coloring(True)
        status_record = views.save_new("Project assets by status")
        saved_status = status_record.content.asset_status
        assert status_record.to_data()["version"] == 4
        assert saved_status.property_name == ASSET_STATUS and saved_status.color_enabled
        assert saved_status.selected_key is None
        await views.set_status_coloring(False)
        original_record = views.save_new("Project assets with original materials")
        assert not original_record.content.asset_status.color_enabled
        version_two = status_record.to_data()
        version_two["version"] = 2
        version_two["content"]["asset_status"].pop("color_enabled")
        version_two["content"]["asset_status"].pop("transparencies")
        version_two["content"]["asset_status"]["selected_key"] = value_key("Installed")
        assert ViewRecord.from_data(version_two).content.asset_status.color_enabled
        version_two["content"]["asset_status"]["selected_key"] = None
        assert not ViewRecord.from_data(version_two).content.asset_status.color_enabled
        version_three = status_record.to_data()
        version_three["version"] = 3
        version_three["content"]["asset_status"].pop("transparencies")
        assert ViewRecord.from_data(version_three).content.asset_status.transparencies == ()
        await views.set_status_transparency(value_key("Installed"), 65)
        transparent_record = views.save_new("Transparent original materials")
        assert not transparent_record.content.asset_status.color_enabled
        assert dict(transparent_record.content.asset_status.transparencies)[value_key("Installed")] == 65
        invalid = transparent_record.to_data()
        invalid["content"]["asset_status"]["transparencies"][0][1] = 101
        expect_raises(lambda: ViewRecord.from_data(invalid), "transparency")
        checks.append("saved views capture Color or Original mode and custom status colors; schema 1 loads and schema 2 derives its mode from the prior selection")

        await views.exit()
        assert section.snapshot == original_section, (section.snapshot, original_section)
        await colors_settled()
        for path, binding in prior_bindings.items():
            expect_material(stage, path, binding)
        assert not controller.inspection_active
        expect_camera(viewport, camera_path)
        checks.append("Exit restores the original section and existing Object Colors scheme")

        root.Save()
        await context.close_stage_async()
        await context.open_stage_async(str(SCENE))
        await frames(30)
        stage = context.get_stage()
        await colors_settled()
        section = get_runtime_state()
        section.sync_stage()
        assert section.stage is stage and views.stage is stage
        viewport = viewport_utility.get_active_viewport()
        viewport.camera_path = "/World/ReviewCamera"
        camera_path = str(viewport.camera_path)
        assert {record.id for record in views.saved_views()} == {
            north.id, south.id, status_record.id, original_record.id, transparent_record.id
        }
        assert views.content is None, "Opening a scene activated a saved view"
        await views.open(status_record.id)
        assert views.content.asset_status == saved_status
        assert views.membership.colored == 3
        for path in ("/World/North", "/World/Hidden"):
            expect_material(stage, path, controller.overrides.material_root + "/C59A14F")
        expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
        expect_material(stage, "/World/Other", ORIGINAL)
        status_box = section.box
        stage.GetPrimAtPath("/World/South").GetAttribute(ASSET_STATUS).Set("Installed")
        await views.refresh()
        assert views.membership.colored == 3 and section.box == status_box
        expect_material(stage, "/World/South", controller.overrides.material_root + "/C59A14F")
        expect_material(stage, "/World/Other", ORIGINAL)
        stage.GetPrimAtPath("/World/South").GetAttribute(ASSET_STATUS).Set("Planned")
        await views.refresh()
        assert views.membership.colored == 3 and section.box == status_box
        expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
        await views.select_status(value_key("Planned"))
        expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
        expect_material(stage, "/World/North", controller.overrides.material_root + "/C59A14F")
        assert views.store.get(status_record.id).content.asset_status == saved_status
        await views.open(original_record.id)
        assert not views.content.asset_status.color_enabled and views.membership.colored == 0
        await views.set_status_color(value_key("Planned"), "#4E79A7")
        await views.select_status(value_key("Planned"))
        for path in SAME_PROJECT + ("/World/Other",):
            expect_material(stage, path, ORIGINAL)
        await views.set_status_coloring(True)
        expect_material(stage, "/World/South", controller.overrides.material_root + "/C4E79A7")
        expect_material(stage, "/World/North", controller.overrides.material_root + "/C59A14F")
        assert section.box == status_box
        checks.append("scene Save/reopen retains Color and Original modes; Refresh follows status values, Original allows unpainted edits, and Color restores all groups without moving the box")
        await views.open(transparent_record.id)
        assert not views.content.asset_status.color_enabled
        assert abs(opacity(stage, "/World/North") - .35) < 1e-6
        assert dict(views.content.asset_status.transparencies)[value_key("Installed")] == 65
        await views.set_status_coloring(True)
        assert abs(opacity(stage, "/World/North") - .35) < 1e-6
        checks.append("saved transparency survives scene Save/reopen and mode changes; schema 3 defaults to 0% and invalid percentages are rejected")
        membership = await views.open(north.id)
        assert set(membership.matching) == set(SAME_PROJECT)
        assert membership.colored == 3 and views.content.asset_status is None
        assert views.content.box == saved_north.box
        legacy_box = section.snapshot
        await views.set_status_property(ASSET_STATUS)
        await views.set_status_color(value_key("Installed"), "#4E79A7")
        await views.set_status_color(value_key("Planned"), "#F28E2B")
        assert views.content.asset_status.selected_key is None and views.membership.colored == 3
        for path in ("/World/North", "/World/Hidden"):
            expect_material(stage, path, controller.overrides.material_root + "/C4E79A7")
        expect_material(stage, "/World/South", controller.overrides.material_root + "/CF28E2B")
        await views.set_status_coloring(False)
        assert views.membership.colored == 0
        for path in SAME_PROJECT + ("/World/Other",):
            expect_material(stage, path, ORIGINAL)
        assert section.snapshot == legacy_box
        await views.open(north.id)
        checks.append("legacy saved highlights remain readable; selecting a status property migrates to all-status colors and Original clears them")
        reopened_box = section.box
        expect_camera(viewport, camera_path)
        checks.append("normal scene Save/reopen shares named views without activating or moving the camera")

        asset(stage, "/World/LaterAddition", PROJECT.value, 200, UsdShade.Material.Get(stage, ORIGINAL))
        fresh = await views.refresh()
        assert set(fresh.matching) == set(SAME_PROJECT + ("/World/LaterAddition",))
        assert section.box == reopened_box, "Refresh moved the saved section"
        expect_material(stage, "/World/LaterAddition", controller.overrides.material_root + "/CE15759")
        fitted = await views.refit(1.0)
        assert "/World/LaterAddition" in fitted.visible
        assert section.box != reopened_box
        assert max(corner[0] for corner in section.box.corners()) > 200
        assert views.store.get(north.id).content == saved_north, "Refit silently updated the named view"
        expect_camera(viewport, camera_path)
        checks.append("new matching assets join on Refresh, retain saved box, and enter the box only on Refit")

        for path in SAME_PROJECT + ("/World/LaterAddition",):
            UsdGeom.Imageable(stage.GetPrimAtPath(path)).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
        box_before_empty_refit = section.box
        none_visible = await views.refit(1.0)
        assert len(none_visible.matching) == 4 and not none_visible.visible
        assert len(none_visible.hidden) == 4
        assert none_visible.colored == 4 and not none_visible.color_issues
        expect_material(stage, "/World/LaterAddition", controller.overrides.material_root + "/CE15759")
        assert section.box == box_before_empty_refit
        assert "Box unchanged" in views.status
        expect_camera(viewport, camera_path)
        checks.append("Refit with no visible match refreshes counts and colors while retaining the section")
        await views.exit()
        await colors_settled()
        assert not controller.inspection_active

        # Run the three recovery cases independently so one failure does not hide the others.
        recovery_failures = []
        for path in SAME_PROJECT[:2]:
            UsdGeom.Imageable(stage.GetPrimAtPath(path)).GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)

        prior_section = section.snapshot
        await views.preview(IDENTITY_PROJECT_ID, PROJECT)
        scope = views._scope
        real_close = scope.close

        async def close_failure():
            raise RuntimeError("injected Object Colors close failure")

        scope.close = close_failure
        try:
            observed_error = None
            try:
                await views.exit()
            except RuntimeError as exc:
                observed_error = exc
            assert observed_error is not None or "close failure" in views.status, views.status
            assert section.snapshot == prior_section, "Exit left the section box active after color close failed"
            assert views.content is None and views.source_id is None, "Exit retained a partial inspection"
            checks.append("Exit restores the section and clears inspection even when Object Colors close fails")
        except Exception:
            recovery_failures.append(("failed color-scope close", traceback.format_exc()))
        finally:
            scope.close = real_close
            await scope.close()
            await views.exit()
            await colors_settled()

        prior_section = section.snapshot
        prior_bindings = {path: material_path(stage, path) for path in ("/World/North", "/World/Other")}
        await views.preview(IDENTITY_PROJECT_ID, PROJECT)
        views.destroy()
        await frames(30)
        try:
            assert section.snapshot == prior_section, "Extension teardown left the section box active"
            assert not controller.inspection_active, "Extension teardown retained the color lease"
            for path, binding in prior_bindings.items():
                expect_material(stage, path, binding)
            checks.append("destroying Project View during inspection restores the section and color scheme")
        except Exception:
            recovery_failures.append(("destroy during active inspection", traceback.format_exc()))
        finally:
            if section.snapshot != prior_section:
                section.edit(box=prior_section.box, enabled=prior_section.enabled,
                             show_box=prior_section.show_box,
                             saved_position_path=prior_section.saved_position_path)
            views = ProjectViews()
            await colors_settled()

        try:
            alt_choices = await views.discover(ALT_PROPERTY)
            assert [(choice.project_id, choice.count) for choice in alt_choices] == [(PROJECT, 1)]
            await views.preview(ALT_PROPERTY, PROJECT)
            alternate = views.save_new("Alternate attribute")
            assert alternate.content.property_name == ALT_PROPERTY
            await views.open(north.id)
            assert views.content.property_name == IDENTITY_PROJECT_ID
            assert views.property_name == IDENTITY_PROJECT_ID, "Panel still selects the previous property"
            assert {(choice.project_id, choice.count) for choice in views.choices} == {(PROJECT, 4), (OTHER, 1)}, (
                "Panel still offers IDs from the previous property", views.choices
            )
            checks.append("opening a saved view selects its recorded Project ID attribute and choices")
        except Exception:
            recovery_failures.append(("saved view property selection", traceback.format_exc()))
        finally:
            await views.exit()
            await colors_settled()

        if recovery_failures:
            raise AssertionError("\n\n".join(f"{name}:\n{error}" for name, error in recovery_failures))

        make_centimetre_scene()
        await context.close_stage_async()
        await context.open_stage_async(str(SCENE_CM))
        await frames(30)
        stage = context.get_stage()
        controller = await colors_settled()
        section = get_runtime_state()
        section.sync_stage()
        assert section.stage is stage and views.stage is stage and controller.stage is stage
        assert abs(UsdGeom.GetStageMetersPerUnit(stage) - 0.01) < 1e-12
        viewport = viewport_utility.get_active_viewport()
        viewport.camera_path = "/World/ReviewCamera"
        camera_path = str(viewport.camera_path)
        choices = await views.discover(IDENTITY_PROJECT_ID)
        assert len(choices) == 107, len(choices)
        assert {(choice.project_id, choice.count) for choice in choices if choice.project_id == CM_PROJECT} == {
            (CM_PROJECT, 3)
        }
        last_bulk = views.filtered_choices("BULK-104")
        assert len(last_bulk) == 1 and last_bulk[0].project_id == ProjectId.from_value("BULK-104")
        bulk = await views.preview(IDENTITY_PROJECT_ID, last_bulk[0].project_id)
        assert bulk.matching == ("/World/Bulk104",) and bulk.visible == bulk.matching
        assert bulk.colored == 0 and not views.status_properties and not views.status_groups
        expect_camera(viewport, camera_path)
        await views.exit()
        await colors_settled()
        checks.append("the 105th distinct Project ID remains searchable and can be previewed")

        original_section = section.snapshot
        original_bindings = {path: material_path(stage, path) for path in (
            "/World/OnlyHidden", "/World/CmWest", "/World/CmEast"
        )}
        original_colors_enabled = controller.overrides.enabled
        original_root = stage.GetRootLayer().ExportToString()
        assert not controller.inspection_active and views.content is None
        try:
            await views.preview(IDENTITY_PROJECT_ID, INVISIBLE)
        except ValueError as exc:
            assert "none has visible geometry" in str(exc), str(exc)
        else:
            raise AssertionError("Preview accepted an ID whose only asset is hidden")
        assert section.snapshot == original_section
        assert not controller.inspection_active and controller.overrides.enabled == original_colors_enabled
        assert views.content is None and stage.GetRootLayer().ExportToString() == original_root
        for path, binding in original_bindings.items():
            expect_material(stage, path, binding)
        expect_camera(viewport, camera_path)
        checks.append("Preview refuses a no-visible project without changing section, colors, model or camera")

        centimetres = await views.preview(IDENTITY_PROJECT_ID, CM_PROJECT, padding_metres=1.0)
        assert set(centimetres.visible) == {"/World/CmWest", "/World/CmEast"}
        assert centimetres.hidden == ("/World/CmHidden",)
        expect_box_bounds(section.box, (-101, -101, -101), (601, 101, 101), tolerance=1e-5)
        assert section.enabled and centimetres.colored == 0
        expect_camera(viewport, camera_path)
        await views.exit()
        await colors_settled()
        checks.append("a centimetre scene fits visible assets with exactly 100 stage units of padding per side")

        await verify_section_defaults(views, checks)

        result = {"passed": checks}
        (OUTPUT / "kit-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("PROJECT_VIEW_KIT_PASS", json.dumps(checks))
        APP.post_quit(0)
    except Exception:
        error = traceback.format_exc()
        print(error)
        (OUTPUT / "kit-results.json").write_text(json.dumps({"passed": checks, "error": error}, indent=2), encoding="utf-8")
        APP.post_quit(1)
    finally:
        if views is not None:
            views.destroy()


asyncio.ensure_future(verify())
