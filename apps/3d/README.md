# MeshAi

Turn 2D pictures into textured 3D models (GLB) with TRELLIS.2 on a Mac, from a
web page: one picture at a time or a whole folder, a library with several
versions of each model, and a 3D viewer. Works from a phone on the same network.

```bash
python3 start.py      # http://localhost:8300
```

Needs a working [trellis-mac](https://github.com/shivampkumar/trellis-mac) set-up
beside this folder (`../trellis-mac`, or set `trellis_dir` in
`server/settings.local.json`). Folders the Bulk tab may open go in the same file:

```json
{"folders": [{"name": "Desktop", "path": "~/Desktop"}]}
```

| API | |
|---|---|
| `POST /api/make?name=&versions=&filename=` | body: the picture; queues versions |
| `GET /api/models`, `GET /api/models/{slug}` | the library |
| `POST /api/models/{slug}/more` | `{picture, versions}` more versions |
| `POST /api/models/{slug}/rename`, `DELETE /api/models/{slug}[/versions/{id}]` | |
| `GET /api/browse?path=`, `POST /api/bulk` | `{folder, versions, skip_existing}` |
| `GET /api/jobs`, `POST /api/jobs/{id}/stop`, `POST /api/batches/{id}/stop` | the queue |
| `GET /api/status` | is TRELLIS ready, loaded, busy |

The 3D viewer is Google's [model-viewer](https://modelviewer.dev) (Apache-2.0), in `web/vendor/`.
