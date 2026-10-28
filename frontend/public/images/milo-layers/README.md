# Milo cutout layers

Canvas coordinates refer to the original 1312 × 1199 mascot.

- `clean-plate.png`: image-edited underpainting with eyes, nose, paper and holding paw removed. It restores the previously hidden face and torso.
- `left-eye.png`, `right-eye.png`: separate eye whites with the iris area restored.
- `left-iris.png`, `right-iris.png`: original blue iris and pupil pixels, extracted by contour and color.
- `nose.png`: original nose cutout.
- `resume.png`: original résumé cutout, with the holding paw excluded.
- `paw.png`: original holding paw, rendered over the résumé using the same transform. The paper region beneath the paw remains occluded; these two layers must stay together.
- `manifest.json`: original placement and native dimensions of the cropped PNGs.

`frontend/scripts/milo-cutouts.js` records the extraction contours and eye-white reconstruction. Runtime loads the exported PNGs, not a mesh or displacement filter. Every visible cutout is drawn at its native dimensions inside one uniform display scale. Motion uses only translation and rotation; paper and paw share a transform.

The homepage uses gaze-led cutout motion at fixed amplitude 1.0.
