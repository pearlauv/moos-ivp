# Vehicle drawing layers

In a mission's `ProcessConfig = pMarineViewer`, set:

```moos
vehicles_layer = bottom
```

- `top` (default): vehicles are drawn after other graphics, preserving existing
  behavior.
- `bottom`: vehicles are drawn after the background/hash but before `VIEW_*`
  graphics, operating area, datum, drop points, and mouse-coordinate text.

Vehicle bodies, labels, bearing lines, and trails share the selected layer.
This is a global vehicle-layer setting, not a per-vehicle or arbitrary numeric
z-order. Values are case-insensitive; invalid values are rejected without changing
the current layer. `vehicles_viewable`, trail visibility, and name visibility
continue to work independently. Polygon transparency still applies: a partially
transparent polygon allows a bottom-layer vehicle to show through.

## Native rendering regression

From the checkout root, after configuring/building IvP:

```bash
cmake --build build/ivp --target pMarineViewer test_pMarineViewer_layers -j4
bin/test_pMarineViewer_layers
```

The opt-in target is excluded from normal builds. It needs an OpenGL display;
on headless Linux run under Xvfb (e.g. `xvfb-run -a bin/test_pMarineViewer_layers`
if that wrapper is installed). It does not connect to MOOS or touch running
missions. The test renders an opaque green polygon overlapping a red vehicle,
reads actual framebuffer pixels, and checks default/top, bottom, switching,
invalid values, and vehicle visibility.
