# Onshape tool datasheet (mirror of `src/onshape_mcp/tools.py`)

The same content is exposed at runtime via the `tool_datasheet` MCP tool.
Keep this file in sync with `tools.py` — the `as_prompt_block()` renderer is
the source of truth the LLM sees, but humans want a doc.

## Sketching

| Tool                | Purpose                                                   | Pre               | Post               |
|---------------------|-----------------------------------------------------------|-------------------|--------------------|
| `sketch.start`      | Open a sketch on a plane or face                          | —                 | `sketch.active=true` |
| `sketch.rectangle` | Two-corner rectangle                                      | `sketch.active`   | —                  |
| `sketch.circle`     | Center + radius                                           | `sketch.active`   | —                  |
| `sketch.line`       | Segment p1→p2                                             | `sketch.active`   | —                  |
| `sketch.spline`     | Open spline through control points                        | `sketch.active`   | —                  |
| `sketch.dimension`  | Drive a dimension to a value                              | `sketch.active`   | —                  |
| `sketch.constrain`  | Add a geometric constraint                                | `sketch.active`   | —                  |
| `sketch.mirror`     | Mirror sketch entities across a line                      | `sketch.active`   | —                  |
| `sketch.exit`       | Close sketch                                              | `sketch.active`   | `sketch.active=false` |

## Features

| Tool                  | Purpose                                                  | Pre                 |
|-----------------------|----------------------------------------------------------|---------------------|
| `feature.extrude`     | Extrude a sketch region                                  | `sketch.active=false` |
| `feature.revolve`     | Revolve sketch around an axis                            | `sketch.active=false` |
| `feature.fillet`      | Round selected edges                                     | —                   |
| `feature.chamfer`     | Bevel selected edges                                     | —                   |
| `feature.shell`       | Hollow a body                                            | —                   |
| `feature.pattern`     | Linear / circular pattern                                | —                   |
| `feature.mirror_body` | Mirror bodies across a plane                             | —                   |

## Selection / view

| Tool            | Purpose                          |
|-----------------|----------------------------------|
| `select.face`   | Click a face in the viewport     |
| `select.edge`   | Click an edge                    |
| `select.body`   | Click a body (viewport or tree)  |
| `view.fit`      | Reframe camera to fit all bodies |
| `view.rotate`   | Orbit camera by (dx, dy)         |

## Assembly

| Tool                  | Purpose                          |
|-----------------------|----------------------------------|
| `assembly.mate`       | Create a mate between entities   |
| `assembly.pattern`    | Pattern instances in assembly    |

## Document / meta

| Tool          | Purpose                                          |
|---------------|--------------------------------------------------|
| `doc.open`    | Navigate to a doc URL                            |
| `doc.save`    | Force-save                                       |
| `ui.undo`     | Send Undo (Ctrl/Cmd+Z)                           |
| `ui.redo`     | Send Redo (Ctrl/Cmd+Shift+Z)                     |
