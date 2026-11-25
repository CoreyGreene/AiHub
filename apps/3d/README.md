# 3D AI

Turn 2D pictures into textured 3D models (GLB) with TRELLIS.2 on a Mac, from a
web page: one picture at a time or a whole folder, a library with several
versions of each model, and a 3D viewer. Works from a phone on the same network. It's one of the tools in AiHub
(`apps/3d`).

Open its tile in AiHub (`python3 start.py` at the repo root, then
http://localhost:8000); it shows at `/3d/`. On its own:

```bash
python3 start.py      # http://localhost:8300
```

Needs a working [trellis-mac](https://github.com/shivampkumar/trellis-mac) set-up
beside the AiHub folder (`trellis_dir`, `../../../trellis-mac` from `apps/3d`; set
another in `server/settings.local.json`). Its models are in trellis-mac's
`local-model/`, not in the hub's models folder. Folders the Bulk tab may open go in the same file:

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
