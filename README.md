# Project View for USD Composer

Save named construction inspection areas by Project ID. A view remembers its Project ID property and value, section box, Asset Status property, display mode, selected row, status colors, and transparency percentages. It finds matching assets again when you open it, so new assets with the same ID join the view. You navigate the camera yourself; this version does not save or move the camera.

## Install

Download the [Project View source ZIP](https://github.com/sdg-xs/project.view/archive/refs/heads/main.zip), or clone this repository. Install [Section Box](https://github.com/sdg-xs/usd-composer-section-box) and [Object Colors](https://github.com/sdgnemyno/usd-composer-object-colors) separately as `section.box` and `object.color` under the same extension search directory.

This version requires Object Colors with `object_colors.appearance.Appearance` and inspection transparency support. At the time of the October 5, 2026 verification, those changes existed in the local Object Colors checkout but had not been published upstream. An older Object Colors installation will prevent Project View from loading.

In PowerShell, choose a directory for your extensions and run:

```powershell
New-Item -ItemType Directory -Force C:\Omniverse\extensions | Out-Null
Set-Location C:\Omniverse\extensions
git clone https://github.com/sdg-xs/project.view.git project.view
```

If you download the ZIP, extract and rename its top-level folder to `project.view` under `C:\Omniverse\extensions`. That folder must directly contain `config/extension.toml`. Do not point Kit at a ZIP file or at a folder containing an extra nested repository folder.

Add `C:\Omniverse\extensions` to your app's extension search paths and enable `project.view` in the Extension Manager. Alternatively, add these arguments to your existing Kit or Composer launch command:

```text
--ext-folder C:\Omniverse\extensions --enable project.view
```

Kit enables its Section Box and Object Colors dependencies. Open the panel through **Window > Project View**. Save work in an already-running Composer session before relaunching it with these options.

This version targets Kit 110.2 with an RTX viewport and a Z-up USD stage. The stage must have valid metres-per-unit metadata. The running Object Colors and Section Box services must be attached to the active viewport's scene.

If Kit cannot find `project.view`, check the search path and folder layout above. If it reports a missing `section.box` or `object.color` dependency, install that extension separately. This repository contains an extension, not a standalone Composer application.

## Verification

On October 5, 2026, all 30 integration checks passed in a private Kit 110.2 process. The suite covers extension startup, panel controls, project discovery, section fitting, status colors, transparency, scene save/reopen, and cleanup. See [the results](verification/kit-results.json) and [the verification script](tests/verify_kit.py). These checks use generated test scenes.

## Create a view

1. Open the **Project View** panel. Click **Scan** to discover properties and Project IDs.
2. The **Project ID property** dropdown defaults to **Identity Data / Project ID**. Select another property when a model uses a different ID field.
3. Search for a Project ID and click it to preview its assets. The selected ID button gets a highlighted background. The section box restores that project's saved default, or fits all visible matching assets with one metre of padding on each side. **Color** mode applies every Asset Status group's color within the project. It uses the previous status property if available, otherwise the first discovered field. Your camera does not move.
4. Use the **Asset Status** dropdown to choose among fields found on this project's assets. Below it, **Original** restores original materials and **Color** shows all status colors. The rows show the property's current statuses and counts. Assets outside the project keep their original materials.
5. Click a status row to select it. Row selection keeps the display mode and other status colors unchanged. Click a row's color circle to choose from Object Colors' 40-color palette. In **Color** mode, that group repaints immediately. In **Original** mode, the choice is stored until you choose **Color**.
Each row has a transparency slider and a percentage button between its status and color circle. Drag the slider and release to apply a percentage. Click **100%** to hide that group's geometry completely; the button then shows **0%**, which restores the group and resets its slider to 0%. The slider stays responsive while the scene updates; rapid changes apply the latest value. Transparency works in both **Original** and **Color** modes. At 0%, the selected mode keeps its normal appearance, including any transparency already in original materials. Other statuses keep their own percentages, and geometry outside the selected project or status remains visible. Intermediate percentages depend on the scene material and renderer: some RTX modes fade the surface without revealing geometry behind it. **100%** uses visibility and hides the geometry regardless of material.

6. Navigate to the area yourself and adjust the box using the Section Box panel or its viewport handles. The **Show Box** tick in Project View shows or hides the outline and handles without changing clipping; it stays in sync with the same tick in Section Box. Changing the status property, selected row, display mode, or colors keeps the box and camera in place.
7. Enter a name and choose **Save New**. Use Composer's normal **Save** to write the view into the USD scene file. Use **Save As** for an anonymous new scene.

You can save several named views for one Project ID. **Update** replaces a saved view's box and status settings with the current inspection. **Rename** changes its label without changing the view. **Delete** removes its scene record; Composer Save commits that deletion to disk. Selecting a new Project ID starts in **Color** mode.

## Save or reset a project's section

After adjusting the box, choose **Save section** to make its position, size, and rotation the default for this exact Project ID property and value. Future clicks on that ID restore the saved section. **Reset section** removes the default and immediately fits all visible project assets with one metre of padding per side. Later ID clicks fit the project's current assets again.

**Save section** and **Reset section** sit side by side above the full-width **Exit view** button. They preserve the camera, Original or Color mode, and palette choices. Use Composer **Save**, or **Save As** for an anonymous scene, to persist the default or its removal. Project defaults are independent of named views, which retain their own section and color settings.

## Reopen a view

Choose **Open** beside a saved view to restore its section box, Asset Status property, display mode, selected row, colors, and transparency. Project View rescans the current scene for assets with the saved exact property and ID, then discovers their current statuses. It leaves your current camera alone. Clicking a Project ID also rescans its assets, then restores its saved section default or fits a new preview.

Views saved with the original schema still open with their whole-project highlight. Choosing an Asset Status property switches them to the current status controls. Earlier status views with a selected status or a legacy highlight now open in **Color** mode and show all status colors. Those with neither open in **Original** mode.

Views saved before transparency controls default to 0%.

Hidden assets remain hidden. The panel reports hidden matches and assets without usable geometry. Automatic fitting requires visible geometry; an already saved view can still reopen when its matches have since disappeared or become hidden.

**Exit view** restores the section box and Object Colors display you had before entering Project View. Closing the panel only hides its controls; use Exit view to end the inspection. Project View does not change an asset's authored materials or visibility.

Saved views are root-layer scene records. A coworker needs the saved scene and the same extensions. On a read-only scene you can open and inspect views but cannot change saved views or project section defaults.

## Development

The integration design and current scope are in [DESIGN.md](DESIGN.md). Fixed Project ID and Asset Status property names remain undecided; the dropdowns support the properties discovered in each model. Isolated Kit verification lives under [tests](tests/) and runs with `run-verify-kit.ps1` once the local Kit 110.2 installation is available.
