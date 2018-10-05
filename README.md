# Image background transform
Transform 3D View background images using G, R, S, similar to Blender transform tools.
* `SHIFT` + `ALT` + `B` to start the operator, then
* `G`, `R`, `S`, to select transform mode (translate, rotate, scale, respectively)
* `A` to transform all images at once
* `CTRL` to snap to closest values
* `X`/`Y` to constrain to axis
* `SHIFT` for precision mode
* `MOUSEWHEEL` to choose a different image

Note that the pivot mode (3D Cursor, Individual Origins, etc.) is considered during transformation, to allow precise scaling and rotating.

![Background image transform](https://raw.githubusercontent.com/LesFeesSpeciales/blender-scripts-docs/master/BG_xform_edit.gif "Background image transform")  

### Known issues
* The transforms don't work properly in Camera view.

-----

## License

Blender scripts shared by **Les Fées Spéciales** are, except where otherwise noted, licensed under the GPLv2 license.
