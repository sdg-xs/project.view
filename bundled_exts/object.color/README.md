# Object Colors for USD Composer

Color a whole USD stage by an object property, source file, or model. Edit colors in a legend and save the active scheme with the scene.

Each final Xform is one object. Coloring gives its whole subtree one solid color, including glass. Meshes and other child prims are not counted separately. Disable colors to restore the original materials and transparency.

Xforms containing lights or cameras are excluded so coloring cannot replace the sky or lighting materials.

This extension targets Kit 110.2 on Windows. See [supported data and limitations](docs/reference.md) and [verification results](docs/verification.md).

## Enable the extension

1. Put the `object.color` folder in an extension search directory.
2. Open **Developer > Extensions** in Composer.
3. Add the parent directory of `object.color` to the extension search paths if needed.
4. Search for **Object Colors** and enable it.

The panel opens automatically. Reopen it through **Window > Object Colors**.

## Color the scene

1. Open a USD scene.
2. Choose **Property**, **File**, or **Model** under **Color by**.
3. For Property mode, type beside the search icon to see matching properties as you type. Select a result to apply it.
4. Select **Enable colors**.
5. Click a legend swatch to choose another color.

Choose **No color** in the palette to reveal the underlying material for that group. Clear **Enable colors** to restore the whole scene.

Click **Refresh** after changing the scene or its properties. Existing assignments remain stable. Expand **notices** for objects that cannot be colored.

Use Composer's Undo and Redo commands for scheme and swatch changes. Save the scene to retain its scheme and enabled state.

## Project View transparency

The inspection API accepts `Appearance(color, transparency)` as well as existing color strings. Percentages are whole numbers from 0 to 100. Below 100%, temporary USD Preview Surface or OmniPBR materials author the requested opacity; `color=None` preserves the source colors and textures. RTX rendering of intermediate values depends on the scene material and renderer, and can fade a surface without revealing geometry behind it. At 100%, the matching geometry is hidden so it leaves no visible silhouette, shadow, or reflection. Lowering the percentage restores it, and 0% in Original mode restores authored material transparency. Unsupported material networks are reported when fading them below 100%. Overrides remain in the owned session layer and are removed when the inspection ends.

## Run verification

Run the commands from the extension directory:

```powershell
./run-verify.ps1
./run-verify-kit.ps1
./run-verify.ps1 -Test tests/benchmark.py
```

The scripts use the Kit installation at `C:\kit-app-template\_build\windows-x86_64\release\kit`. Pass `-KitRoot` to select another installation. The Kit check starts a separate process and generates its own scene. Results and screenshots go to `verification/`.

For static typechecking, install `mypy` into `verification/typecheck` using Kit's Python, then run `./run-typecheck.ps1`.
