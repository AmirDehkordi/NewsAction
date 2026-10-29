"""NA-14: the paper's figures, tables, captions and replication run (PRD NA-14).

- ``style``: the one print style (the dataviz skill's palette, fonts, sizes, interval helpers, file export);
- ``sources``: the upstream files, their row keys and the trace check (every plotted number names its cell);
- ``data``: each figure's CSV, assembled from the upstream rows it plots;
- ``render`` and ``fig1_hero_car`` … ``fig8_explain_move``, ``appendix``: one module per figure, drawn from
  its CSV only;
- ``tables``, ``keys``, ``captions``: the paper tables, their machine-readable keys and the captions that cite
  them;
- ``paper``: ``make paper``, the offline rebuild with its digest check; ``contract``: the data contract.

Nothing in this package calls the decision-model client, ``newsaction.lock``, ``load_targets`` or
``build_reactions``: it reads stored outputs only (``artifacts/NA-03`` … ``NA-13``, ``work/strategy``).
"""
