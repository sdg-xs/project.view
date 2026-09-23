# Project View for USD Composer

Save named construction inspection areas by Project ID. A view remembers its Project ID property and value, section box, and highlight choice. It finds matching assets again when you open it, so new assets with the same ID join the view. You navigate the camera yourself; this first version does not save or move the camera.

## Install

Put `project.view`, `section.box`, and `object.color` under the same Kit extension search directory. Enable `project.view` in your app's Extension Manager if one is available, or launch Kit with `--ext-folder <parent-directory> --enable project.view`. Kit enables its Section Box and Object Colors dependencies. Save work in an already-running Composer session before relaunching it with these options.

This version targets Kit 110.2 with an RTX viewport and a Z-up USD stage. The stage must have valid metres-per-unit metadata. The running Object Colors and Section Box services must be attached to the active viewport's scene.

## Create a view

1. Open the **Project View** panel. Click **Scan** to discover properties and Project IDs.
2. The initial property is **Identity Data / Project ID**. Select another property when a model uses a different ID field. Search for an ID and select it.
3. Choose **Preview**. The section box fits visible matching assets with one metre of padding on each side. Matching assets get the selected highlight color; surrounding materials stay original. Your camera does not move.
4. Navigate to the area yourself and adjust the box using the Section Box panel or its viewport handles. Set another highlight color or choose **No highlight** to see original materials while keeping the section and Project ID.
5. Enter a name and choose **Save New**. Use Composer's normal **Save** to write the view into the USD scene file. Use **Save As** for an anonymous new scene.

You can save several named views for one Project ID. **Update** replaces a saved view's box and color settings with the current inspection. **Rename** changes its label without changing the view. **Delete** removes its scene record; Composer Save commits that deletion to disk.

## Reopen and refresh

Choose **Open** beside a saved view to restore its section box and color choice. Project View rescans the current scene for assets with the saved exact property and ID. It leaves your current camera alone. **Refresh assets** updates matching and color assignments without moving the box. **Refit section** changes the box to include the current visible matches using the displayed padding. If nothing visible can be fitted, the current box stays in place and the panel reports the count.

Hidden assets remain hidden. The panel reports hidden matches and assets without usable geometry. Preview refuses an empty fit; an already saved view can still reopen when its matches have since disappeared or become hidden.

**Exit view** restores the section box and Object Colors display you had before entering Project View. Closing the panel only hides its controls; use Exit view to end the inspection. Project View does not change an asset's authored materials or visibility.

Saved views are root-layer scene records. A coworker needs the saved scene and the same extensions. On a read-only scene you can open and inspect views but cannot create, update, rename, or delete their records.

## Development

The integration design and current scope are in [DESIGN.md](DESIGN.md). Isolated Kit verification lives under [tests](tests/) and runs with `run-verify-kit.ps1` once the local Kit 110.2 installation is available.
