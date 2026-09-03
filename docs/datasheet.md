# Tool datasheet

Mirror of `src/onshape_mcp/tools.py`. The same content is exposed at
runtime via the `tool_datasheet` MCP tool. Keep this in sync; the
`as_prompt_block()` renderer is the source of truth the LLM sees, but
I want a human-readable version too.

## Sketch

| Tool | What it does | Needs |
|------|--------------|-------|
| `sketch.start` | Open a sketch on a plane or face | |
| `sketch.rectangle` | Two-corner rectangle | `sketch.active` |
| `sketch.circle` | Center + radius | `sketch.active` |
| `sketch.line` | Segment p1 to p2 | `sketch.active` |
| `sketch.spline` | Open spline through control points | `sketch.active` |
| `sketch.dimension` | Drive a dimension to a value | `sketch.active` |
| `sketch.constrain` | Add a geometric constraint | `sketch.active` |
| `sketch.mirror` | Mirror sketch entities across a line | `sketch.active` |
| `sketch.exit` | Close sketch | `sketch.active` |

## Features

| Tool | What it does | Needs |
|------|--------------|-------|
| `feature.extrude` | Extrude a sketch region | `sketch.active=false` |
| `feature.revolve` | Revolve sketch around an axis | `sketch.active=false` |
| `feature.fillet` | Round selected edges | |
| `feature.chamfer` | Bevel selected edges | |
| `feature.shell` | Hollow a body | |
| `feature.pattern` | Linear or circular pattern | |
| `feature.mirror_body` | Mirror bodies across a plane | |

## Selection and view

| Tool | What it does |
|------|--------------|
| `select.face` | Click a face in the viewport |
| `select.edge` | Click an edge |
| `select.body` | Click a body (viewport or feature tree) |
| `view.fit` | Reframe camera to fit all bodies |
| `view.rotate` | Orbit camera by drag |

## Assembly

| Tool | What it does |
|------|--------------|
| `assembly.mate` | Create a mate between entities |
| `assembly.pattern` | Pattern instances in an assembly |

## Document and meta

| Tool | What it does |
|------|--------------|
| `doc.open` | Navigate to a doc URL |
| `doc.save` | Force-save |
| `ui.undo` | Send Undo (Ctrl+Z) |
| `ui.redo` | Send Redo (Ctrl+Shift+Z) |
