# Patch series index

This directory holds **two independent series**. They target different source
trees, are applied by different build stages, and must never be mixed.

| Directory | Applies to | Filenames | Count |
|-----------|-----------|-----------|-------|
| [`kernel/`](kernel/README.md) | mainline Linux tarball, `config/versions.env` → `KERNEL_VERSION` | `0001-…` … `00NN-…` | 38 |
| [`aic8800/`](aic8800/README.md) | AIC8800 vendor driver tarball, `radxa-pkg/aic8800` @ pinned commit | `aic8800-0001-…` | 4 |

Both follow the same philosophy — a curated series on a pinned upstream tarball
rather than a fork — so each can be rebased onto a newer upstream by replaying
the series.

**Telling them apart:** kernel patches are bare-numbered (`0007-pwm-add-…`);
AIC8800 patches always carry the `aic8800-` prefix, so a filename alone is
unambiguous in a grep result, an editor tab, or a build log. If a patch has no
prefix, it belongs to the kernel.

They are also independently versioned: bumping `KERNEL_VERSION` has no effect on
the AIC8800 series, and bumping the AIC8800 commit has no effect on the kernel
series.
