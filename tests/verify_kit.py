"""Exercise named project views in a private headless Kit process."""

import asyncio
import json
from pathlib import Path
import sys
import traceback

import omni.kit.app
import omni.kit.undo
import omni.kit.viewport.utility as viewport_utility
import omni.usd
import omni.ui as ui
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

from object_colors.extension import get_controller
from project_view.records import IDENTITY_PROJECT_ID, ProjectId
from project_view.views import ProjectViews
from section_box.extension import get_runtime_state
from section_box.model import SectionBox


APP = omni.kit.app.get_app()
OUTPUT = Path(__file__).resolve().parent.parent / "verification"
SCENE = OUTPUT / "project-view-fixture.usda"
SCENE_CM = OUTPUT / "project-view-centimetres.usda"
PROJECT = ProjectId.from_value("P-01514")
OTHER = ProjectId.from_value("P-02000")
CM_PROJECT = ProjectId.from_value("CM-WORK")
INVISIBLE = ProjectId.from_value("INVISIBLE")
ORIGINAL = "/World/Looks/Original"
SAME_PROJECT = ("/World/North", "/World/South", "/World/Hidden")
ALT_PROPERTY = "custom:alternateProjectId"


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


def asset(stage, path, project_id, x, material, *, hidden=False):
    root = UsdGeom.Xform.Define(stage, path)
    root.AddTranslateOp().Set(Gf.Vec3d(x, 0, 0))
    if project_id is not None:
        root.GetPrim().CreateAttribute(IDENTITY_PROJECT_ID, Sdf.ValueTypeNames.String, custom=True).Set(project_id)
    cube = UsdGeom.Cube.Define(stage, path + "/Shape")
    cube.CreateSizeAttr(2.0)
    UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(material)
    if hidden:
        UsdGeom.Imageable(root).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    return root


def make_scene():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    material = source_material(stage)
    asset(stage, "/World/North", PROJECT.value, 0, material)
    asset(stage, "/World/South", PROJECT.value, 5, material)
    asset(stage, "/World/Hidden", PROJECT.value, 100, material, hidden=True)
    other = asset(stage, "/World/Other", OTHER.value, 15, material)
    other.GetPrim().CreateAttribute(ALT_PROPERTY, Sdf.ValueTypeNames.String, custom=True).Set(PROJECT.value)
    asset(stage, "/World/Surroundings", None, -12, material)
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 30))
    stage.GetRootLayer().Export(str(SCENE))


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

        views = ProjectViews()
        choices = await views.discover(IDENTITY_PROJECT_ID)
        assert {(choice.project_id, choice.count) for choice in choices} == {(PROJECT, 3), (OTHER, 1)}, choices
        assert ALT_PROPERTY in views.properties
        assert [(choice.project_id, choice.count) for choice in await views.discover(ALT_PROPERTY)] == [(PROJECT, 1)]
        membership = await views.preview(IDENTITY_PROJECT_ID, PROJECT)
        assert set(membership.matching) == set(SAME_PROJECT), membership
        assert set(membership.visible) == set(SAME_PROJECT[:2]), membership
        assert membership.hidden == ("/World/Hidden",), membership
        assert membership.colored == 3 and not membership.color_issues, membership
        assert section.enabled and section.show_box
        expect_box_bounds(section.box, (-2, -2, -2), (7, 2, 2))
        for path in SAME_PROJECT:
            expect_material(stage, path, controller.overrides.material_root + "/CE15759")
        for path in ("/World/Other", "/World/Surroundings"):
            expect_material(stage, path, ORIGINAL)
        assert context.get_selection().get_selected_prim_paths() == selected
        assert stage.GetRootLayer().ExportToString() == root_before_preview, "Preview authored the model"
        expect_camera(viewport, camera_path)
        checks.append("exact Identity Data ID discovers placed assets; hidden geometry is excluded from the 1 m fit")
        checks.append("Preview clips and highlights matches, preserves original surroundings, selection, model and camera")

        await views.set_highlight(None)
        assert views.content.highlight_color is None and views.content.chosen_color == "#E15759"
        for path in SAME_PROJECT + ("/World/Other",):
            expect_material(stage, path, ORIGINAL)
        await views.set_highlight("#E15759")
        expect_material(stage, "/World/North", controller.overrides.material_root + "/CE15759")
        expect_camera(viewport, camera_path)
        checks.append("No highlight reveals original materials and re-enabling uses the chosen color")

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
        assert {record.id for record in views.saved_views()} == {north.id, south.id}
        assert views.content is None, "Opening a scene activated a saved view"
        membership = await views.open(north.id)
        assert set(membership.matching) == set(SAME_PROJECT)
        assert views.content.box == saved_north.box
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
        assert bulk.colored == 1
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
        assert section.enabled and centimetres.colored == 3
        expect_camera(viewport, camera_path)
        await views.exit()
        await colors_settled()
        checks.append("a centimetre scene fits visible assets with exactly 100 stage units of padding per side")

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
