# pylot-bem documentation

The write side: mesh a hull at a floating condition, solve it with Capytaine,
assemble the results. Carries the command line and the standalone application.

| | |
|---|---|
| [`api.md`](api.md) | The reference. What to call and what comes back |
| [`spec/03_mesh_pipeline.md`](spec/03_mesh_pipeline.md) | Base shape plus condition to a solver-ready mesh |
| [`spec/04_solving.md`](spec/04_solving.md) | Bodies, lids, problems, and the dataset that comes back |
| [`spec/06_ui_and_integration.md`](spec/06_ui_and_integration.md) | The standalone application, and the deferred DAVE work |
| [`spec/07_tech_stack.md`](spec/07_tech_stack.md) | Dependencies, and why each is there |
| [`spec/09_ui_options.md`](spec/09_ui_options.md) | Every option and derived field the interface shows |
| [`spec/10_cli.md`](spec/10_cli.md) | Three commands, and why only three |
| [`spec/11_api.md`](spec/11_api.md) | Why the API is shaped the way it is |

## What is not here

`pylot-bem` depends on `pylot-db`, and so does its documentation. The
**reference frames**, the **storage model**, the **entities**, **matching** and
the **delivery of a database** are documented in `pylot-db`, and docstrings
here cite them as *pylot-db's spec NN*.

That direction is deliberate and worth preserving: this package may refer to
its dependency's documentation, and the dependency must never refer back.

The numbering has gaps because the specification was split when the packages
became separate repositories. Keeping the original numbers means every citation
in the source still resolves.
